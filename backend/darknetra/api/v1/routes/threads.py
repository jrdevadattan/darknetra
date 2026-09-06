from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from darknetra.agent import service
from darknetra.agent.events import TERMINAL, append, stream
from darknetra.agent.models import Message, Thread, ToolCall
from darknetra.api.pagination import page_rows
from darknetra.api.v1.schemas import threads as dto
from darknetra.api.v1.schemas.activity import ExecutionSnapshot
from darknetra.api.v1.schemas.common import EvidenceRef, Page
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission as P
from darknetra.cases.models import Case
from darknetra.db import get_session
from darknetra.decisions.models import Finding
from darknetra.errors import Conflict, NotFound, Validation
from darknetra.evidence.models import Evidence

router = APIRouter(tags=["threads"])


@router.get(
    "/cases/{case_id}/threads/{thread_id}/runs/{run_id}/execution", response_model=ExecutionSnapshot
)
async def execution_snapshot(
    case_id: UUID,
    thread_id: UUID,
    run_id: UUID,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    from darknetra.agent.activity import snapshot

    return await snapshot(db, case_id, thread_id, run_id)


@router.post("/cases/{case_id}/threads", response_model=dto.Thread, status_code=201)
async def create_thread(
    case_id: UUID,
    data: dto.ThreadCreate,
    request: Request,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    return await service.thread_dto(
        db, await service.create_thread(db, case, actor, data, request.app.state.settings)
    )


@router.get("/cases/{case_id}/threads", response_model=Page[dto.Thread])
async def list_threads(
    case_id: UUID,
    status: Literal["OPEN", "CLOSED"] | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(Thread).where(Thread.case_id == case_id)
    if status:
        query = query.where(Thread.status == status)
    rows, next_cursor, total = await page_rows(
        db, query, Thread, limit=limit, cursor=cursor, newest_by=Thread.created_at
    )
    return Page(
        items=[await service.thread_dto(db, row) for row in rows],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/cases/{case_id}/threads/{thread_id}", response_model=dto.Thread)
async def get_thread(
    case_id: UUID,
    thread_id: UUID,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await service.thread_dto(db, await service.get_thread(db, case_id, thread_id))


@router.patch("/cases/{case_id}/threads/{thread_id}", response_model=dto.Thread)
async def patch_thread(
    case_id: UUID,
    thread_id: UUID,
    data: dto.ThreadPatch,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await service.thread_dto(
        db, await service.patch_thread(db, access[1], access[0], thread_id, data)
    )


@router.get("/cases/{case_id}/threads/{thread_id}/messages", response_model=Page[dto.Message])
async def list_messages(
    case_id: UUID,
    thread_id: UUID,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.get_thread(db, case_id, thread_id)
    query = select(Message).where(Message.case_id == case_id, Message.thread_id == thread_id)
    if cursor:
        previous = await db.scalar(
            select(Message).where(
                Message.case_id == case_id, Message.thread_id == thread_id, Message.id == cursor
            )
        )
        if previous is None:
            raise NotFound("Resource not found")
        from sqlalchemy import tuple_

        query = query.where(tuple_(Message.at, Message.id) > (previous.at, previous.id))
    rows = list((await db.scalars(query.order_by(Message.at, Message.id).limit(limit + 1))).all())
    return Page(
        items=[service.message_dto(row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.post(
    "/cases/{case_id}/threads/{thread_id}/messages", response_model=dto.RunRef, status_code=202
)
async def post_message(
    case_id: UUID,
    thread_id: UUID,
    data: dto.MessageCreate,
    request: Request,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    run = await service.post_message(
        db, case_id, access[0], thread_id, data, request.app.state.settings
    )
    try:
        job_id = await request.app.state.jobs.submit(
            "thread.run",
            lambda: service.execute_run(
                request.app, case_id, thread_id, run.id, access[0], data.content
            ),
            key=f"run:{run.id}",
        )
    except Exception:
        from datetime import UTC, datetime

        run.status, run.finished_at = "ERROR", datetime.now(UTC)
        run.error = {"code": "UNAVAILABLE", "message": "Job runner unavailable"}
        await append(db, case_id, run.id, "run.error", run.error)
        await append(
            db,
            case_id,
            run.id,
            "run.finished",
            {"status": "ERROR", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0},
        )
        await db.commit()
        raise
    if not hasattr(request.app.state, "runtime_jobs"):
        request.app.state.runtime_jobs = {}
    request.app.state.runtime_jobs[run.id] = job_id
    return dto.RunRef(run_id=run.id, thread_id=thread_id, status=run.status)


@router.get("/cases/{case_id}/threads/{thread_id}/runs/{run_id}", response_model=dto.Run)
async def get_run(
    case_id: UUID,
    thread_id: UUID,
    run_id: UUID,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    run = await service.get_run(db, case_id, thread_id, run_id)
    calls = list(
        (
            await db.scalars(
                select(ToolCall)
                .where(ToolCall.case_id == case_id, ToolCall.run_id == run_id)
                .order_by(ToolCall.seq)
            )
        ).all()
    )
    outputs = []
    for call in calls:
        evidence = list(
            (
                await db.scalars(
                    select(Evidence).where(
                        Evidence.case_id == case_id, Evidence.id.in_(call.result_evidence_ids)
                    )
                )
            ).all()
        )
        outputs.append(
            dto.ToolCall(
                id=call.id,
                seq=call.seq,
                tool=call.tool,
                args=call.args,
                status=call.status,
                policy_decision=call.policy_decision,
                started_at=call.started_at,
                finished_at=call.finished_at,
                duration_ms=call.duration_ms,
                evidence=[EvidenceRef(id=e.id, code=e.code) for e in evidence],
                error=call.error,
            )
        )
    return dto.Run(
        id=run.id,
        thread_id=run.thread_id,
        status=run.status,
        harness=run.harness,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cost_usd=float(run.cost_usd),
        error=run.error,
        tool_calls=outputs,
        replayed_from_run_id=run.replayed_from_run_id,
    )


@router.get(
    "/cases/{case_id}/threads/{thread_id}/runs/{run_id}/events",
    response_class=Response,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def events(
    case_id: UUID,
    thread_id: UUID,
    run_id: UUID,
    request: Request,
    last_event_id: str | None = Header(None),
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.get_run(db, case_id, thread_id, run_id)
    try:
        after = int(last_event_id or "0")
        if after < 0:
            raise ValueError
    except ValueError:
        raise Validation("Last-Event-ID must be a nonnegative sequence") from None
    return EventSourceResponse(
        stream(request.app.state.session_factory, case_id, run_id, after),
        ping=15,
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/cases/{case_id}/threads/{thread_id}/runs/{run_id}/cancel", status_code=202)
async def cancel(
    case_id: UUID,
    thread_id: UUID,
    run_id: UUID,
    request: Request,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    run = await service.get_run(db, case_id, thread_id, run_id)
    if run.status not in TERMINAL:
        run.cancel_requested = True
        await record(
            db,
            actor=access[0],
            action="run.cancel_requested",
            case_id=case_id,
            thread_id=thread_id,
            run_id=run_id,
        )
        await db.commit()
        job_id = getattr(request.app.state, "runtime_jobs", {}).get(run_id)
        if job_id:
            await request.app.state.jobs.cancel(job_id)
        await db.refresh(run)
        if run.status not in TERMINAL:
            from datetime import UTC, datetime

            run.status, run.finished_at = "CANCELLED", datetime.now(UTC)
            await append(db, case_id, run_id, "run.cancelled", {})
            await append(
                db,
                case_id,
                run_id,
                "run.finished",
                {
                    "status": "CANCELLED",
                    "cost_usd": float(run.cost_usd),
                    "tokens_in": run.tokens_in,
                    "tokens_out": run.tokens_out,
                },
            )
    return Response(status_code=202)


@router.post("/cases/{case_id}/threads/{thread_id}/pin", status_code=204)
async def pin(
    case_id: UUID,
    thread_id: UUID,
    data: dto.PinRequest,
    access: tuple[Actor, Case] = Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    thread = await service.get_thread(db, case_id, thread_id, lock=True)
    if access[1].status != "OPEN" or thread.status != "OPEN":
        raise Conflict("Case or thread is read-only")
    finding = await db.scalar(
        select(Finding).where(Finding.case_id == case_id, Finding.id == data.finding_id)
    )
    if finding is None:
        raise NotFound("Resource not found")
    ids = set(thread.pinned_finding_ids)
    if data.pinned:
        ids.add(data.finding_id)
    else:
        ids.discard(data.finding_id)
    thread.pinned_finding_ids = sorted(ids, key=str)
    await record(
        db,
        actor=access[0],
        action="thread.pin_changed",
        case_id=case_id,
        thread_id=thread_id,
        target_type="FINDING",
        target_id=finding.id,
        detail={"pinned": data.pinned},
    )
    return Response(status_code=204)
