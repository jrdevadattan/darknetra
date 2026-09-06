"""The sole path from public-source bytes to model-visible excerpts."""

import hashlib
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from darknetra.audit.service import digest, record
from darknetra.capture.fetcher import Fetched
from darknetra.errors import AppError
from darknetra.policy.engine import check
from darknetra.tools.contracts import ToolContext, ToolError, ToolSpec
from darknetra.tools.presentation import emit_tool_activity


class CaptureResult(BaseModel):
    evidence_code: str
    evidence_id: UUID
    duplicate: bool
    title: str | None = None
    excerpt: str
    source_class: str
    captured_at: datetime
    quarantined: bool


async def _capture(
    ctx: ToolContext, *, spec: ToolSpec, locator: str, fetch: Callable[[], Awaitable[Fetched]]
) -> CaptureResult:
    from darknetra.evidence.service import get_text, ingest_bytes

    case = await check(ctx, spec, {}, consume=True)
    if ctx.parent_call_id:
        await emit_tool_activity(ctx, spec, ctx.parent_call_id, status="running", phase="fetching")
    fetched = await fetch()
    if ctx.parent_call_id:
        await emit_tool_activity(
            ctx, spec, ctx.parent_call_id, status="running", phase="persisting"
        )
    extension = {"text/html": "html", "application/json": "json", "text/plain": "txt"}.get(
        fetched.mime, "bin"
    )
    async with ctx.session_factory() as session:
        result = await ingest_bytes(
            session,
            case=case,
            actor=ctx.actor,
            data=fetched.data,
            filename=f"capture.{extension}",
            settings=ctx.settings,
            source_class=spec.source_class or "OSINT_SURFACE",
            origin="MONITOR" if ctx.watchlist_item_id else "CAPTURE",
            locator=fetched.url,
            meta={
                "http_status": fetched.status,
                "http_headers": fetched.headers,
                "requested_locator_hash": digest(locator),
            },
            requester_kind="WATCHLIST_ITEM"
            if ctx.watchlist_item_id
            else ("THREAD" if ctx.thread_id else "USER"),
            requester_id=ctx.watchlist_item_id or ctx.thread_id or ctx.actor.user_id,
        )
        await record(
            session,
            actor=ctx.actor,
            action="capture.completed",
            case_id=ctx.case_id,
            thread_id=ctx.thread_id,
            run_id=ctx.run_id,
            target_type="EVIDENCE",
            target_id=result.evidence.id,
            detail={"locator_hash": digest(locator), "source_class": spec.source_class},
            result_hash=hashlib.sha256(fetched.data).hexdigest(),
        )
        await session.commit()
        evidence = result.evidence
        if ctx.parent_call_id:
            await emit_tool_activity(
                ctx,
                spec,
                ctx.parent_call_id,
                status="running",
                phase="captured",
                ids=[evidence.id],
                codes=[evidence.code],
            )
        await ctx.emit(
            {
                "type": "store.changed",
                "data": {
                    "case_id": str(ctx.case_id),
                    "tables": ["evidence", "observations", "chunks"],
                    "evidence_codes": [evidence.code],
                },
            }
        )
        excerpt = ""
        if evidence.status != "QUARANTINED":
            try:
                text, _ = await get_text(session, ctx.case_id, evidence.id, ctx.settings)
                excerpt = text[:1200]
            except Exception:
                # Persistence succeeds even when optional text extraction does not.
                excerpt = ""
        return CaptureResult(
            evidence_code=evidence.code,
            evidence_id=evidence.id,
            duplicate=result.duplicate,
            excerpt=excerpt,
            source_class=evidence.source_class,
            captured_at=evidence.captured_at,
            quarantined=evidence.status == "QUARANTINED",
        )


async def capture(
    ctx: ToolContext, *, spec: ToolSpec, locator: str, fetch: Callable[[], Awaitable[Fetched]]
) -> CaptureResult:
    try:
        return await _capture(ctx, spec=spec, locator=locator, fetch=fetch)
    except (ToolError, AppError) as exc:
        async with ctx.session_factory() as session:
            await record(
                session,
                actor=ctx.actor,
                action="capture.denied"
                if exc.code in {"POLICY_DENIED", "RATE_LIMITED", "NETWORK_REQUIRED"}
                else "capture.failed",
                case_id=ctx.case_id,
                thread_id=ctx.thread_id,
                run_id=ctx.run_id,
                detail={
                    "locator_hash": digest(locator),
                    "source_class": spec.source_class,
                    "code": exc.code,
                },
            )
            await session.commit()
        raise
