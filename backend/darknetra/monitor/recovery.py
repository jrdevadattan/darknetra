"""Durable attempt bookkeeping for the single-process monitoring scheduler."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.cases.models import Case
from darknetra.monitor.models import MonitorRun, WatchlistItem
from darknetra.monitor.service import effective_interval


def run_lock_key(case_id, item_id):
    return int.from_bytes(
        hashlib.sha256((str(case_id) + str(item_id)).encode()).digest()[:8], "big", signed=True
    )


async def interrupt_run(db, run, *, settings, reason):
    """Caller holds the item's advisory lock; no evidence or hits are manufactured."""
    now = datetime.now(UTC)
    run.status = "ERROR"
    run.finished_at = now
    run.errors = {
        **run.errors,
        "execution": {
            "code": "UNAVAILABLE",
            "message": "Monitoring attempt interrupted; collection was not completed",
            "reason": reason,
        },
    }
    item = await db.scalar(
        select(WatchlistItem)
        .where(WatchlistItem.case_id == run.case_id, WatchlistItem.id == run.item_id)
        .with_for_update()
    )
    if item:
        # A newer completed attempt must retain its own schedule and result.
        if item.last_run_at is None or item.last_run_at <= run.started_at:
            item.last_run_at = now
            item.next_run_at = (
                now + timedelta(seconds=effective_interval(item.interval_seconds, settings))
                if item.active
                else None
            )
            item.state = {
                **item.state,
                "last_run_id": str(run.id),
                "last_status": "ERROR",
                "interruption_reason": reason,
            }
    await record(
        db,
        actor=Actor("SYSTEM", None),
        action="monitor.interrupted",
        case_id=run.case_id,
        target_type="watchlist_item",
        target_id=run.item_id,
        detail={"run_id": str(run.id), "reason": reason, "status": "ERROR"},
    )


async def recover_interrupted_monitors(db, case_id, *, settings, before):
    """Called per case at startup; locks also protect against an active collector."""
    candidates = list(
        await db.execute(
            select(MonitorRun.id, MonitorRun.item_id)
            .where(
                MonitorRun.case_id == case_id,
                MonitorRun.status == "RUNNING",
                MonitorRun.started_at <= before,
            )
            .order_by(MonitorRun.started_at.desc(), MonitorRun.id)
        )
    )
    recovered = 0
    for run_id, item_id in candidates:
        if not await db.scalar(
            select(func.pg_try_advisory_xact_lock(run_lock_key(case_id, item_id)))
        ):
            continue
        # The case lock serializes attempt/item updates with configuration changes.
        await db.execute(select(Case.id).where(Case.id == case_id).with_for_update())
        run = await db.scalar(
            select(MonitorRun)
            .where(
                MonitorRun.case_id == case_id,
                MonitorRun.id == run_id,
                MonitorRun.status == "RUNNING",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            continue
        await interrupt_run(db, run, settings=settings, reason="APPLICATION_RESTART")
        recovered += 1
    return recovered


async def persist_interruption(session_factory, *, case_id, run_id, item_id, settings, reason):
    async with session_factory() as db:
        # The failed transaction has released its lock. If a new attempt has won,
        # startup recovery can close the old record without disturbing that work.
        if not await db.scalar(
            select(func.pg_try_advisory_xact_lock(run_lock_key(case_id, item_id)))
        ):
            return
        await db.execute(select(Case.id).where(Case.id == case_id).with_for_update())
        run = await db.scalar(
            select(MonitorRun)
            .where(
                MonitorRun.case_id == case_id,
                MonitorRun.id == run_id,
                MonitorRun.status == "RUNNING",
            )
            .with_for_update()
        )
        if run is not None:
            await interrupt_run(db, run, settings=settings, reason=reason)
            await db.commit()
