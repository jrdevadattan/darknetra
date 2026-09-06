"""One invocation path for schema, authorization, capture policy, audit and events."""

import asyncio
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from darknetra.agent.models import Run, ToolCall
from darknetra.audit.service import digest, record
from darknetra.auth.actor import Actor
from darknetra.errors import AppError
from darknetra.policy.engine import check
from darknetra.tools.contracts import ToolContext, ToolError, ToolResult
from darknetra.tools.presentation import emit_tool_activity, evidence_codes
from darknetra.tools.registry import REGISTRY


def evidence_ids(value: Any) -> list[UUID]:
    found: set[UUID] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_id" or (key == "id" and "code" in value):
                try:
                    found.add(UUID(str(item)))
                except ValueError:
                    pass
            found.update(evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(evidence_ids(item))
    return sorted(found, key=str)


async def invoke(ctx: ToolContext, name: str, args: dict[str, Any]) -> ToolResult:
    started = time.monotonic()
    at = datetime.now(UTC)
    call_id = uuid4()
    spec = REGISTRY.get(name)
    # The bound case always wins, even if a provider invents a case_id parameter.
    bounded = {k: v for k, v in args.items() if k != "case_id"}
    hashed = digest(bounded)
    cached = False
    captured_ids: set[UUID] = set()
    captured_codes: set[str] = set()

    async def track_capture(event: dict[str, Any]) -> None:
        data = event.get("data", {})
        if (
            event.get("type") == "activity.updated"
            and data.get("id") == str(call_id)
            and data.get("phase") == "captured"
        ):
            captured_ids.update(UUID(i) for i in data.get("evidence_ids", []))
            captured_codes.update(evidence_codes(data))
        await ctx.emit(event)

    async def step(status: str, phase: str, result: ToolResult | None = None) -> None:
        activity = await emit_tool_activity(
            ctx,
            spec,
            call_id,
            status=status,
            phase=phase,
            ids=sorted(captured_ids | set(result.evidence_ids if result else []), key=str),
            codes=sorted(captured_codes | set(evidence_codes(result.data) if result else [])),
            duration_ms=int((time.monotonic() - started) * 1000),
            error_code=str(result.error["code"]) if result and result.error else None,
            cached=cached,
        )
        await ctx.emit(
            {
                "type": "run.step",
                "data": {
                    "kind": "tool_call",
                    "tool": activity["tool_name"],
                    "call_id": str(call_id),
                    "parent_id": activity["parent_id"],
                    "status": {
                        "running": "started",
                        "completed": "finished",
                        "denied": "denied",
                        "failed": "error",
                        "cancelled": "error",
                    }[status],
                    "summary": activity["summary"],
                    "cached": cached,
                    "evidence_ids": activity["evidence_ids"],
                    "evidence_codes": activity["evidence_codes"],
                    "duration_ms": activity["duration_ms"],
                    "metadata": {
                        key: activity[key]
                        for key in (
                            "display_name",
                            "integration_id",
                            "adapter_kind",
                            "transport",
                            "agent_role",
                        )
                    },
                    "error": {"code": activity["error_code"], "message": activity["summary"]}
                    if activity["error_code"]
                    else None,
                },
            }
        )

    try:
        await emit_tool_activity(ctx, spec, call_id, status="running", phase="authorizing")
        if ctx.execution_budget is not None:
            ctx.execution_budget.consume_tool()
        if spec is None:
            raise ToolError("VALIDATION", "Unknown tool")
        if ctx.role not in spec.allowed_for:
            raise ToolError("POLICY_DENIED", "Tool is not available to this agent role")
        parsed = spec.input_model.model_validate(bounded)
        await check(ctx, spec, bounded)
        cache_key = f"{name}:{hashed}"
        if cache_key in ctx.cache:
            result, cached = ctx.cache[cache_key], True
        else:
            await step("running", "executing")
            timeout = spec.timeout_s
            if ctx.execution_budget is not None:
                timeout = min(timeout, ctx.execution_budget.remaining_seconds())
            output = await asyncio.wait_for(
                spec.impl(replace(ctx, parent_call_id=call_id, emit=track_capture), parsed),
                timeout=timeout,
            )
            validated = spec.output_model.model_validate(output)
            data = validated.model_dump(mode="json")
            ids = evidence_ids(data)
            if len(validated.model_dump_json()) > spec.max_result_chars:
                result = ToolResult(
                    ok=True,
                    data={
                        "notice": "Result exceeds model context limit; use a smaller query",
                        "evidence_ids": [str(i) for i in ids],
                        "evidence_codes": evidence_codes(data),
                    },
                    evidence_ids=ids,
                    truncated=True,
                )
            else:
                result = ToolResult(ok=True, data=data, evidence_ids=ids)
            ctx.cache[cache_key] = result
    except ValidationError:
        result = ToolResult(
            ok=False,
            error={"code": "VALIDATION", "message": "Tool arguments or result failed validation"},
        )
    except TimeoutError:
        result = ToolResult(ok=False, error={"code": "UNAVAILABLE", "message": "Tool timed out"})
    except (ToolError, AppError) as exc:
        result = ToolResult(
            ok=False, error={"code": exc.code, "message": exc.message, "detail": exc.detail}
        )
    except asyncio.CancelledError:
        result = ToolResult(
            ok=False,
            error={"code": "UNAVAILABLE", "message": "Tool cancelled"},
            evidence_ids=sorted(captured_ids, key=str),
        )
        await step("cancelled", "cancelled", result)
        await persist(ctx, name, hashed, at, started, result, "ERROR", cached, call_id=call_id)
        raise
    except Exception:
        result = ToolResult(
            ok=False, error={"code": "UNAVAILABLE", "message": "Tool could not complete"}
        )
    result.evidence_ids = sorted(set(result.evidence_ids) | captured_ids, key=str)
    status = (
        "DONE"
        if result.ok
        else (
            "DENIED"
            if result.error
            and result.error["code"]
            in {"POLICY_DENIED", "NETWORK_REQUIRED", "RATE_LIMITED", "BUDGET_EXCEEDED"}
            else "ERROR"
        )
    )
    await persist(ctx, name, hashed, at, started, result, status, cached, call_id=call_id)
    await step(
        {"DONE": "completed", "DENIED": "denied", "ERROR": "failed"}[status],
        ("cache_hit" if cached else "complete") if result.ok else "error",
        result,
    )
    return result


async def persist(
    ctx: ToolContext,
    name: str,
    hashed: str,
    at: datetime,
    started: float,
    result: ToolResult,
    status: str,
    cached: bool,
    call_id: UUID | None = None,
) -> None:
    async with ctx.session_factory() as session:
        if ctx.run_id and ctx.thread_id:
            await session.execute(
                select(Run.id)
                .where(Run.case_id == ctx.case_id, Run.id == ctx.run_id)
                .with_for_update()
            )
            seq = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(ToolCall.seq), 0)).where(
                            ToolCall.case_id == ctx.case_id, ToolCall.run_id == ctx.run_id
                        )
                    )
                    or 0
                )
                + 1
            )
            session.add(
                ToolCall(
                    id=call_id or uuid4(),
                    case_id=ctx.case_id,
                    run_id=ctx.run_id,
                    thread_id=ctx.thread_id,
                    seq=seq,
                    tool=name,
                    args={"redacted": True, "sha256": hashed},
                    args_hash=hashed,
                    policy_decision={"allowed": status != "DENIED"},
                    status=status,
                    started_at=at,
                    finished_at=datetime.now(UTC),
                    duration_ms=int((time.monotonic() - started) * 1000),
                    result_hash=digest(result.model_dump(mode="json")),
                    result_evidence_ids=result.evidence_ids,
                    error=result.error,
                    cached=cached,
                    requester_kind="THREAD",
                    requester_id=ctx.thread_id,
                )
            )
        audit_actor = Actor("MODEL", None) if ctx.run_id else ctx.actor
        await record(
            session,
            actor=audit_actor,
            action="tool.call",
            case_id=ctx.case_id,
            thread_id=ctx.thread_id,
            run_id=ctx.run_id,
            detail={
                "tool": name,
                "call_id": str(call_id) if call_id else None,
                "args_hash": hashed,
                "status": status,
                "cached": cached,
                "error_code": result.error.get("code") if result.error else None,
            },
            result_hash=digest(result.model_dump(mode="json")),
        )
        await session.commit()
