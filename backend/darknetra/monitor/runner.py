"""Persist attempts before collection; publish hits and final state atomically."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from darknetra.audit.service import record
from darknetra.cases.models import Case
from darknetra.errors import AppError, Conflict, NotFound, RateLimited
from darknetra.monitor import adapters, dedupe, triage
from darknetra.monitor.alerts import raise_alert
from darknetra.monitor.models import (
    Alert,
    MonitorHit,
    MonitorRun,
    MonitorSeenUrl,
    Watchlist,
    WatchlistItem,
)
from darknetra.monitor.principal import require_execution_actor
from darknetra.monitor.recovery import persist_interruption, run_lock_key
from darknetra.monitor.service import effective_interval
from darknetra.monitor.validation import sources_for
from darknetra.tools.contracts import ToolContext, ToolError


def retry_delay(value, now):
    try:
        until = datetime.fromisoformat(value)
        if until.tzinfo is None:
            return 0
        return min(3600, max(0, int((until - now).total_seconds())))
    except (ValueError, TypeError):
        return 0


async def run_item(db, *, case_id, item_id, actor, settings, session_factory, manual=False):
    run_id = uuid4()
    try:
        return await _run_item(
            db,
            case_id=case_id,
            item_id=item_id,
            actor=actor,
            settings=settings,
            session_factory=session_factory,
            manual=manual,
            run_id=run_id,
        )
    except BaseException as exc:
        # Release the collector's transaction lock before recording its failure
        # separately. Preserve cancellation and the original public exception.
        await db.rollback()
        try:
            await persist_interruption(
                session_factory,
                case_id=case_id,
                run_id=run_id,
                item_id=item_id,
                settings=settings,
                reason="CANCELLED" if isinstance(exc, asyncio.CancelledError) else "RUN_FAILED",
            )
        except Exception:
            logging.getLogger(__name__).error("monitor_interruption_persistence_unavailable")
        raise


async def _run_item(db, *, case_id, item_id, actor, settings, session_factory, manual, run_id):
    from sqlalchemy import func

    key = run_lock_key(case_id, item_id)
    locked = await db.scalar(select(func.pg_try_advisory_xact_lock(key)))
    if not locked:
        raise RateLimited("This monitor item is already running", detail={"retry_after": 5})
    item = await db.scalar(
        select(WatchlistItem)
        .where(WatchlistItem.case_id == case_id, WatchlistItem.id == item_id)
        .execution_options(populate_existing=True)
    )
    case = await db.scalar(select(Case).where(Case.id == case_id))
    if not item or not case:
        raise NotFound("Watchlist item not found")
    watchlist = await db.scalar(
        select(Watchlist).where(Watchlist.case_id == case_id, Watchlist.id == item.watchlist_id)
    )
    if not item.active or not watchlist.active or case.status != "OPEN":
        raise Conflict("Monitoring requires an active item in an open case")
    actor = await require_execution_actor(session_factory, case_id=case_id, actor=actor)
    now = datetime.now(UTC)
    run = MonitorRun(
        id=run_id,
        case_id=case_id,
        item_id=item_id,
        status="RUNNING",
        started_at=now,
        manual=manual,
        sources_run={},
        new_hits=0,
        errors={},
    )
    async with session_factory() as attempt_db:
        attempt_db.add(run)
        await record(
            attempt_db,
            actor=actor,
            action="monitor.started",
            case_id=case_id,
            target_type="watchlist_item",
            target_id=item_id,
            detail={"run_id": str(run_id), "manual": manual, "status": "RUNNING"},
        )
        await attempt_db.commit()
    # Only the attempt is committed above. Captures keep their own transactions;
    # deduplication, hits, alerts and the final outcome remain one transaction.
    run = await db.scalar(
        select(MonitorRun).where(MonitorRun.case_id == case_id, MonitorRun.id == run_id)
    )
    ctx = ToolContext(
        case_id=case_id,
        actor=actor,
        settings=settings,
        session_factory=session_factory,
        watchlist_item_id=item_id,
    )
    sources, errors, failure_counts = {}, {}, dict(item.state.get("failure_counts", {}))
    backoff = dict(item.state.get("source_backoff", {}))
    deferred = set()
    recent = list(
        await db.scalars(
            select(MonitorHit).where(
                MonitorHit.case_id == case_id,
                MonitorHit.item_id == item_id,
                MonitorHit.at >= now - timedelta(hours=24),
            )
        )
    )
    families = {
        reason.partition(":")[2]
        for hit in recent
        for reason in hit.reasons
        if reason.startswith("source_family:")
    }
    retry_after = 0
    collected, source_errors = {}, {}
    source_order = list(item.sources)
    original_config = (item.value_norm, tuple(item.variants), tuple(item.sources))
    # Capture uses its own transaction. Never hold a case/item row lock or an
    # uncommitted case foreign-key insertion while invoking a capture tool.
    for source in source_order:
        try:
            sources_for(item.type, [source], case, settings)
            delay = retry_delay(backoff.get(source), now)
            if delay:
                deferred.add(source)
                raise ToolError(
                    "RATE_LIMITED",
                    "Source retry is deferred",
                    {"retry_after": delay},
                )
            collected[source] = await adapters.collect(db, case, item, source, ctx)
        except (ToolError, AppError) as exc:
            source_errors[source] = exc
        except Exception:
            source_errors[source] = ToolError("UNAVAILABLE", "Monitoring source failed")
    await db.execute(select(Case.id).where(Case.id == case_id).with_for_update())
    await db.refresh(case)
    await db.refresh(item)
    await db.refresh(watchlist)
    if not item.active or not watchlist.active or case.status != "OPEN":
        raise Conflict("Monitoring was disabled while sources were running")
    if original_config != (item.value_norm, tuple(item.variants), tuple(item.sources)):
        raise Conflict("Monitoring configuration changed while sources were running")
    actor = await require_execution_actor(session_factory, case_id=case_id, actor=actor)
    db.add(run)
    await db.flush()
    for source in source_order:
        try:
            if source in source_errors:
                raise source_errors[source]
            hits = collected[source]
            sources[source] = {"status": "DONE", "hits": len(hits)}
            failure_counts[source] = 0
            backoff.pop(source, None)
        except (ToolError, AppError) as exc:
            errors[source] = {"code": exc.code, "message": exc.message, "detail": exc.detail}
            sources[source] = {
                "status": "DENIED"
                if exc.code in {"POLICY_DENIED", "NETWORK_REQUIRED", "RATE_LIMITED"}
                else "ERROR"
            }
            if exc.code == "RATE_LIMITED":
                retry_after = max(retry_after, int(exc.detail.get("retry_after", 60)))
                if source not in deferred:
                    backoff[source] = (
                        now + timedelta(seconds=max(1, int(exc.detail.get("retry_after", 60))))
                    ).isoformat()
            elif exc.code not in {"POLICY_DENIED", "NETWORK_REQUIRED"}:
                failure_counts[source] = failure_counts.get(source, 0) + 1
                backoff[source] = (
                    now + timedelta(seconds=min(3600, 60 * 2 ** min(failure_counts[source] - 1, 6)))
                ).isoformat()
            await record(
                db,
                actor=actor,
                action="monitor.source_denied"
                if sources[source]["status"] == "DENIED"
                else "monitor.source_failed",
                case_id=case_id,
                target_type="watchlist_item",
                target_id=item_id,
                detail={"source": source, "code": exc.code},
            )
            if failure_counts.get(source, 0) >= 3:
                day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                previous = await db.scalar(
                    select(Alert.id).where(
                        Alert.case_id == case_id,
                        Alert.item_id == item_id,
                        Alert.kind == "MONITOR_ERROR",
                        Alert.at >= day_start,
                        Alert.diversity["source"].astext == source,
                    )
                )
                if not previous:
                    await raise_alert(
                        db,
                        case_id=case_id,
                        actor=actor,
                        kind="MONITOR_ERROR",
                        title="Monitoring source requires attention",
                        summary="A source failed for three consecutive runs; no clean result can be inferred.",
                        evidence_ids=[],
                        item_id=item_id,
                        diversity={"source": source, "error_code": exc.code},
                    )
            continue
        except Exception:
            # Isolate adapter failures without leaking provider input or secrets.
            errors[source] = {"code": "UNAVAILABLE", "message": "Monitoring source failed"}
            sources[source] = {"status": "ERROR"}
            failure_counts[source] = failure_counts.get(source, 0) + 1
            continue
        for hit in hits:
            if hit.source_class not in case.source_policy["allowed_source_classes"]:
                errors[source] = {
                    "code": "POLICY_DENIED",
                    "message": "Source policy changed before triage",
                }
                continue
            fingerprint = dedupe.content_hash(
                hit.locator, hit.excerpt, body_hash=hit.body_hash, event_id=hit.event_id
            )
            url_fingerprint = dedupe.url_hash(hit.locator)
            await db.execute(
                insert(MonitorSeenUrl)
                .values(
                    case_id=case_id,
                    item_id=item_id,
                    url_hash=url_fingerprint,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[MonitorSeenUrl.item_id, MonitorSeenUrl.url_hash],
                    set_={"last_seen_at": now},
                    where=MonitorSeenUrl.case_id == case_id,
                )
            )
            exists = await db.scalar(
                select(MonitorHit.id).where(
                    MonitorHit.case_id == case_id,
                    MonitorHit.item_id == item_id,
                    MonitorHit.content_hash == fingerprint,
                )
            )
            if exists:
                continue
            novel = hit.family not in families
            families.add(hit.family)
            result = triage.score(
                excerpt=hit.excerpt,
                variants=item.variants,
                item_type=item.type,
                source_class=hit.source_class,
                novel=novel,
                families=families,
                image_distance=hit.image_distance,
            )
            alert = None
            if result.alertable:
                kind = {
                    "WALLET": "WALLET_ACTIVITY",
                    "PGP_FINGERPRINT": "KEY_CHANGE",
                    "ONION_DOMAIN": "ONION_STATUS",
                    "IMAGE_HASH": "IMAGE_MATCH",
                }.get(item.type, "NEW_HIT")
                alert = await raise_alert(
                    db,
                    case_id=case_id,
                    actor=actor,
                    kind=kind,
                    title=f"New {item.type.lower()} review signal",
                    summary=f"New stored evidence matched the watchlist item [{hit.evidence_code}]. Analyst review is required.",
                    evidence_ids=list(
                        dict.fromkeys(
                            [hit.evidence_id]
                            + [previous.evidence_id for previous in recent if previous.evidence_id]
                        )
                    )
                    if item.type in {"KEYWORD", "ALIAS"}
                    else [hit.evidence_id],
                    item_id=item_id,
                    diversity=result.diversity,
                )
            row = MonitorHit(
                case_id=case_id,
                run_id=run.id,
                item_id=item_id,
                evidence_id=hit.evidence_id,
                url_hash=url_fingerprint,
                content_hash=fingerprint,
                relevance=result.relevance,
                alertable=result.alertable,
                reasons=result.reasons + ["source_family:" + hit.family],
                alert_id=alert.id if alert else None,
            )
            db.add(row)
            await db.flush()
            recent.append(row)
            run.new_hits += 1
    finished = datetime.now(UTC)
    run.finished_at, run.sources_run, run.errors = finished, sources, errors
    successful = sum(source["status"] == "DONE" for source in sources.values())
    run.status = (
        "DONE"
        if not errors
        else "PARTIAL"
        if successful
        else "RATE_LIMITED"
        if all(e["code"] == "RATE_LIMITED" for e in errors.values())
        else "ERROR"
    )
    item.last_run_at = finished
    item.next_run_at = finished + timedelta(
        seconds=max(
            0 if successful else retry_after, effective_interval(item.interval_seconds, settings)
        )
    )
    item.state = {
        **item.state,
        "failure_counts": failure_counts,
        "last_run_id": str(run.id),
        "last_status": run.status,
        "source_backoff": backoff,
        "suspension_reason": None,
        "interruption_reason": None,
    }
    await record(
        db,
        actor=actor,
        action="monitor.run",
        case_id=case_id,
        target_type="watchlist_item",
        target_id=item_id,
        detail={
            "run_id": str(run.id),
            "status": run.status,
            "new_hits": run.new_hits,
            "sources": sources,
        },
    )
    return run
