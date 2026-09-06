"""Threads and runs: case serialization, persistent messages, verification and budgets."""

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.agent import budget as budgets
from darknetra.agent.claim_checker import extract_claims, verify
from darknetra.agent.context_data import current_context
from darknetra.agent.delegation import DelegationState, ExecutionBudget
from darknetra.agent.events import TERMINAL, append
from darknetra.agent.harness_base import managed_events
from darknetra.agent.models import Message, Run, Thread
from darknetra.api.v1.schemas import threads as dto
from darknetra.api.v1.schemas.common import ActorRef, FindingRef
from darknetra.audit.service import digest, record
from darknetra.auth.actor import Actor
from darknetra.cases.models import Case, CaseMembership
from darknetra.config import Settings
from darknetra.decisions.models import Finding
from darknetra.errors import BudgetExceeded, Conflict, NotFound, Unavailable, Validation
from darknetra.tools.contracts import ToolContext, ToolError


def select_harness(settings: Settings, requested: str | None = None) -> str:
    if settings.harness_mode == "deterministic":
        return "DETERMINISTIC"
    if settings.offline_mode or settings.harness_mode == "offline" or requested == "OFFLINE":
        return "OFFLINE"
    if settings.anthropic_api_key:
        # The pinned SDK resolves its bundled runtime before searching PATH.
        return "CLAUDE"
    return "OFFLINE"


def harness_for(name: str) -> Any:
    if name == "DETERMINISTIC":
        from darknetra.agent.harness_deterministic import DeterministicHarness

        return DeterministicHarness()
    if name == "CLAUDE":
        from darknetra.agent.harness_claude import ClaudeHarness

        return ClaudeHarness()
    from darknetra.agent.harness_offline import OllamaHarness

    return OllamaHarness()


async def recover_interrupted_runs(app: Any) -> int:
    """Single-process startup: terminalize abandoned work without inventing an answer."""
    recovered = 0
    async with app.state.session_factory() as session:
        case_ids = list((await session.scalars(select(Case.id))).all())
    for case_id in case_ids:
        async with app.state.session_factory() as session:
            runs = list(
                (
                    await session.scalars(
                        select(Run)
                        .where(Run.case_id == case_id, Run.status.in_(["QUEUED", "RUNNING"]))
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for run in runs:
                error = {
                    "code": "UNAVAILABLE",
                    "message": "Server stopped before this run completed; submit a new message to continue",
                }
                run.status, run.finished_at, run.error = "ERROR", datetime.now(UTC), error
                await append(session, case_id, run.id, "run.error", error)
                await append(
                    session,
                    case_id,
                    run.id,
                    "run.finished",
                    {
                        "status": "ERROR",
                        "cost_usd": float(run.cost_usd),
                        "tokens_in": run.tokens_in,
                        "tokens_out": run.tokens_out,
                    },
                )
                await record(
                    session,
                    actor=Actor("SYSTEM", None),
                    action="run.recovered",
                    case_id=case_id,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    detail={"status": "ERROR", "reason": "interrupted_by_restart"},
                )
                recovered += 1
            await session.commit()
    return recovered


async def get_thread(
    db: AsyncSession, case_id: UUID, thread_id: UUID, *, lock: bool = False
) -> Thread:
    query = select(Thread).where(Thread.case_id == case_id, Thread.id == thread_id)
    if lock:
        query = query.with_for_update()
    thread = await db.scalar(query)
    if thread is None:
        raise NotFound("Resource not found")
    return thread


async def get_run(db: AsyncSession, case_id: UUID, thread_id: UUID, run_id: UUID) -> Run:
    run = await db.scalar(
        select(Run).where(Run.case_id == case_id, Run.thread_id == thread_id, Run.id == run_id)
    )
    if run is None:
        raise NotFound("Resource not found")
    return run


async def thread_dto(db: AsyncSession, thread: Thread) -> dto.Thread:
    active = await db.scalar(
        select(Run.id).where(
            Run.case_id == thread.case_id,
            Run.thread_id == thread.id,
            Run.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    pinned = (
        list(
            (
                await db.scalars(
                    select(Finding).where(
                        Finding.case_id == thread.case_id, Finding.id.in_(thread.pinned_finding_ids)
                    )
                )
            ).all()
        )
        if thread.pinned_finding_ids
        else []
    )
    return dto.Thread(
        id=thread.id,
        case_id=thread.case_id,
        title=thread.title,
        goal=thread.goal,
        status=thread.status,
        harness=thread.harness,
        summary=thread.summary,
        pinned_findings=[FindingRef(id=f.id, title=f.title, kind=f.kind) for f in pinned],
        budget_usd=float(thread.budget_usd),
        spent_usd=float(thread.spent_usd),
        assignee=ActorRef(kind="USER", id=thread.assignee_id, display="Assigned analyst")
        if thread.assignee_id
        else None,
        created_by=ActorRef(kind="USER", id=thread.created_by, display="Case analyst"),
        created_at=thread.created_at,
        last_message_at=thread.last_message_at,
        active_run_id=active,
    )


def message_dto(message: Message) -> dto.Message:
    return dto.Message(
        id=message.id,
        thread_id=message.thread_id,
        run_id=message.run_id,
        role=message.role,
        blocks=message.blocks or [{"type": "text", "text": message.text}],
        claims=message.claims,
        verification=message.verification or None,
        cost_usd=float(message.cost_usd),
        harness=message.harness,
        at=message.at,
    )


async def create_thread(
    db: AsyncSession, case: Case, actor: Actor, data: dto.ThreadCreate, settings: Settings
) -> Thread:
    if case.status != "OPEN":
        raise Conflict("Case is read-only")
    thread = Thread(
        id=uuid4(),
        case_id=case.id,
        title=data.title,
        goal=data.goal,
        harness=select_harness(settings, data.harness),
        budget_usd=Decimal(str(data.budget_usd)),
        spent_usd=Decimal("0"),
        created_by=actor.user_id,
        pinned_finding_ids=[],
    )
    db.add(thread)
    await db.flush()
    await record(
        db,
        actor=actor,
        action="thread.created",
        case_id=case.id,
        thread_id=thread.id,
        target_type="THREAD",
        target_id=thread.id,
    )
    return thread


async def patch_thread(
    db: AsyncSession, case: Case, actor: Actor, thread_id: UUID, data: dto.ThreadPatch
) -> Thread:
    if case.status != "OPEN":
        raise Conflict("Case is read-only")
    thread = await get_thread(db, case.id, thread_id, lock=True)
    fields = data.model_dump(exclude_unset=True)
    if fields.get("assignee_id"):
        member = await db.scalar(
            select(CaseMembership.user_id).where(
                CaseMembership.case_id == case.id, CaseMembership.user_id == fields["assignee_id"]
            )
        )
        if member is None:
            raise NotFound("Resource not found")
    for key, value in fields.items():
        if key in {"title", "status", "budget_usd"} and value is None:
            raise Validation("Field cannot be null")
        setattr(thread, key, Decimal(str(value)) if key == "budget_usd" else value)
    await record(
        db,
        actor=actor,
        action="thread.updated",
        case_id=case.id,
        thread_id=thread.id,
        detail={"fields": list(fields)},
    )
    await db.flush()
    return thread


async def post_message(
    db: AsyncSession,
    case_id: UUID,
    actor: Actor,
    thread_id: UUID,
    data: dto.MessageCreate,
    settings: Settings,
) -> Run:
    case = await db.scalar(select(Case).where(Case.id == case_id).with_for_update())
    thread = await get_thread(db, case_id, thread_id, lock=True)
    if case is None or case.status != "OPEN" or thread.status != "OPEN":
        raise Conflict("Case or thread is read-only")
    active = int(
        await db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.case_id == case_id, Run.status.in_(["QUEUED", "RUNNING"]))
        )
        or 0
    )
    thread_active = await db.scalar(
        select(Run.id).where(
            Run.case_id == case_id,
            Run.thread_id == thread_id,
            Run.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    if thread_active:
        raise Conflict("A run is already active in this thread")
    if active >= 3:
        raise Unavailable("Case concurrent run limit reached")
    if budgets.remaining(thread) < Decimal("0.25"):
        raise BudgetExceeded("Thread has less than 0.25 USD remaining")
    from darknetra.evidence.models import Evidence

    attachments = []
    for code in data.attachments:
        evidence = await db.scalar(
            select(Evidence).where(
                Evidence.case_id == case_id,
                Evidence.code == code,
                Evidence.status.not_in(["QUARANTINED", "EXPIRED", "FAILED"]),
            )
        )
        if evidence is None:
            raise NotFound("Resource not found")
        attachments.append({"id": str(evidence.id), "code": evidence.code})
    mode = select_harness(settings, thread.harness)
    run = Run(
        id=uuid4(),
        case_id=case_id,
        thread_id=thread_id,
        status="QUEUED",
        harness=mode,
        cost_usd=Decimal("0"),
    )
    db.add(run)
    await db.flush()
    now = datetime.now(UTC)
    db.add(
        Message(
            case_id=case_id,
            thread_id=thread_id,
            run_id=run.id,
            role="USER",
            text=data.content,
            blocks=[
                {"type": "text", "text": data.content},
                *([{"type": "attachment", "evidence": attachments}] if attachments else []),
            ],
            claims=[],
            verification=None,
            at=now,
        )
    )
    thread.last_message_at = now
    await record(
        db, actor=actor, action="run.queued", case_id=case_id, thread_id=thread_id, run_id=run.id
    )
    await db.commit()  # Job can only see a fully committed run and user message.
    return run


async def save_assistant(ctx: ToolContext, text: str, *, revised: bool = False) -> dto.Verification:
    prose, claims = extract_claims(text)
    async with ctx.session_factory() as session:
        verification = await verify(session, ctx.case_id, claims)
        verification.revised = revised
        message = Message(
            id=uuid4(),
            case_id=ctx.case_id,
            thread_id=ctx.thread_id,
            run_id=ctx.run_id,
            role="ASSISTANT",
            text=prose,
            blocks=[{"type": "text", "text": prose}],
            claims=[c.model_dump(mode="json") for c in claims],
            verification=verification.model_dump(),
            harness=None,
            at=datetime.now(UTC),
            cost_usd=Decimal("0"),
        )
        session.add(message)
        await session.flush()
        await append(
            session,
            ctx.case_id,
            ctx.run_id,
            "message.completed",
            {"message": message_dto(message).model_dump(mode="json")},
        )
        await record(
            session,
            actor=Actor("MODEL", None),
            action="message.completed",
            case_id=ctx.case_id,
            thread_id=ctx.thread_id,
            run_id=ctx.run_id,
            detail={"verified": verification.ok, "unverified_count": verification.unverified_count},
        )
        await session.commit()
        return verification


async def execute_run(
    app: Any, case_id: UUID, thread_id: UUID, run_id: UUID, actor: Actor, prompt: str
) -> None:
    factory = app.state.session_factory
    settings = app.state.settings

    async def emit(event: dict[str, Any]) -> None:
        async with factory() as session:
            await append(session, case_id, run_id, event["type"], event.get("data", {}))
            await session.commit()

    ctx = ToolContext(
        case_id,
        actor,
        factory,
        settings,
        thread_id=thread_id,
        run_id=run_id,
        emit=emit,
        agent_id=run_id,
    )
    cost = Decimal("0")
    tokens_in = tokens_out = 0
    partial = ""
    terminal = "DONE"
    error = None
    cached = None
    replay_key = None
    delegation = None
    cost_complete = True
    activity_started = False

    async def root_activity(status: str, summary: str) -> None:
        await emit(
            {
                "type": "activity.updated",
                "data": {
                    "id": str(run_id),
                    "parent_id": None,
                    "kind": "agent",
                    "label": "Case lead",
                    "agent_role": "CASE_LEAD",
                    "status": status,
                    "phase": {
                        "running": "working",
                        "completed": "complete",
                        "failed": "error",
                        "cancelled": "cancelled",
                    }[status],
                    "summary": summary,
                },
            }
        )

    try:
        async with factory() as session:
            run = await get_run(session, case_id, thread_id, run_id)
            thread = await get_thread(session, case_id, thread_id)
            if run.cancel_requested or run.status in TERMINAL:
                terminal = "CANCELLED" if run.cancel_requested else run.status
                return
            run.status, run.started_at = "RUNNING", datetime.now(UTC)
            mode, goal, remaining = run.harness, thread.goal, float(budgets.remaining(thread))
            history_rows = list(
                (
                    await session.scalars(
                        select(Message)
                        .where(
                            Message.case_id == case_id,
                            Message.thread_id == thread_id,
                            Message.run_id != run_id,
                        )
                        .order_by(Message.at.desc())
                        .limit(20)
                    )
                ).all()
            )
            history = [
                {"role": row.role.lower(), "content": row.text}
                for row in reversed(history_rows)
                if row.role == "USER"
                or (row.role == "ASSISTANT" and row.verification and row.verification.get("ok"))
            ]
            context, ctx.context_evidence_codes = await current_context(session, thread, run_id)
            if context:
                history.append({"role": "user", "content": context})
            # A follow-up with the same words can mean something different after prior turns.
            replay_key = digest({"prompt": prompt, "goal": goal, "history": history})
            if settings.demo_mode:
                from darknetra.agent.replay import lookup

                cached = await lookup(session, case_id, replay_key, mode)
                if cached:
                    run.replayed_from_run_id = cached[0]
            await append(
                session,
                case_id,
                run_id,
                "run.started",
                {
                    "run_id": str(run_id),
                    "thread_id": str(thread_id),
                    "harness": mode,
                    "budget_usd": remaining,
                    "replayed": cached is not None,
                },
            )
            await session.commit()
        await root_activity("running", "Case lead reviewing the request")
        activity_started = True
        if cached:
            for text in cached[1]:
                await emit({"type": "message.delta", "data": {"text": text}})
                await save_assistant(ctx, text)
            return
        override = getattr(app.state, "harness_factory", None)
        harness_factory = override or harness_for
        harness = harness_factory(mode)
        ctx.execution_budget = ExecutionBudget(deadline=time.monotonic() + 300)
        allocation = Decimal(str(remaining)) / 2
        delegation = DelegationState(
            mode=mode,
            harness_factory=harness_factory,
            parent_budget=allocation,
            worker_pool=allocation,
            execution_budget=ctx.execution_budget,
        )
        ctx.delegation = delegation
        revision_used = False

        async def process(iteration_prompt: str) -> bool:
            nonlocal cost, tokens_in, tokens_out, partial, cost_complete
            needs_revision = False
            parent_remaining = delegation.parent_budget - cost
            if parent_remaining <= 0:
                raise ToolError("BUDGET_EXCEEDED", "Case lead budget exhausted")
            # Claude reports its aggregate usage at ResultMessage; interruption before
            # that point leaves known charges incomplete, never an invented zero bill.
            cost_complete = mode != "CLAUDE"
            async with managed_events(
                harness.run(
                    ctx,
                    iteration_prompt,
                    goal=goal,
                    history=history,
                    budget=float(parent_remaining),
                )
            ) as events:
                async for event in events:
                    async with factory() as session:
                        state = await get_run(session, case_id, thread_id, run_id)
                        if state.cancel_requested:
                            raise asyncio.CancelledError
                    kind = event.get("type")
                    if kind == "assistant":
                        partial = event.get("text", "")
                        await emit({"type": "message.delta", "data": {"text": partial}})
                        check = await save_assistant(ctx, partial, revised=revision_used)
                        needs_revision |= not check.ok
                        partial = ""
                    elif kind == "message.delta":
                        partial += event.get("data", {}).get("text", "")
                        await emit(event)
                    elif kind == "usage":
                        amount = Decimal(str(event.get("cost_usd", 0)))
                        if not amount.is_finite() or amount < 0:
                            raise ToolError("UNAVAILABLE", "Invalid provider usage")
                        cost += amount
                        tokens_in += int(event.get("tokens_in", 0))
                        tokens_out += int(event.get("tokens_out", 0))
                        cost_complete = True
                        if cost > delegation.parent_budget:
                            raise ToolError("BUDGET_EXCEEDED", "Case lead budget exhausted")
                    else:
                        await emit(event)
            return needs_revision

        async with asyncio.timeout(ctx.execution_budget.remaining_seconds()):
            needs_revision = await process(prompt)
            if needs_revision:
                revision_used = True
                await process(
                    prompt
                    + '\nYour previous answer failed citation verification. Revise once: every factual sentence must have valid evidence in this case and match a claims entry. Say "Insufficient evidence." when unsupported. Do not claim confirmation without an exact accepted finding.'
                )
        if partial:
            await save_assistant(ctx, partial, revised=revision_used)
            partial = ""
    except asyncio.CancelledError:
        terminal = "CANCELLED"
        if partial:
            await asyncio.shield(save_assistant(ctx, partial))
    except Exception as exc:
        terminal = (
            "BUDGET"
            if isinstance(exc, TimeoutError)
            or (isinstance(exc, ToolError) and exc.code == "BUDGET_EXCEEDED")
            else "ERROR"
        )
        error = {
            "code": "BUDGET_EXCEEDED"
            if terminal == "BUDGET"
            else exc.code
            if isinstance(exc, ToolError)
            else "UNAVAILABLE",
            "message": "Agent time limit reached"
            if isinstance(exc, TimeoutError)
            else exc.message
            if isinstance(exc, ToolError)
            else "Run could not complete",
        }
        if partial:
            await save_assistant(ctx, partial)
        await save_assistant(
            ctx, "Budget exhausted." if terminal == "BUDGET" else "The model is unavailable."
        )
    finally:
        if delegation is not None:
            cost += delegation.spent
            tokens_in += delegation.tokens_in
            tokens_out += delegation.tokens_out
            cost_complete &= delegation.cost_complete
        if activity_started:
            await root_activity(
                {"DONE": "completed", "CANCELLED": "cancelled"}.get(terminal, "failed"),
                "Provider usage is incomplete"
                if not cost_complete
                else "Case lead completed"
                if terminal == "DONE"
                else "Case lead stopped",
            )
        async with factory() as session:
            run = await get_run(session, case_id, thread_id, run_id)
            if run.status not in TERMINAL:
                thread = await get_thread(session, case_id, thread_id, lock=True)
                run.status, run.finished_at, run.error = terminal, datetime.now(UTC), error
                run.cost_usd, run.tokens_in, run.tokens_out = cost, tokens_in, tokens_out
                budgets.charge(thread, cost)
                if error:
                    await append(session, case_id, run_id, "run.error", error)
                if terminal == "CANCELLED":
                    await append(session, case_id, run_id, "run.cancelled", {})
                await append(
                    session,
                    case_id,
                    run_id,
                    "run.finished",
                    {
                        "status": terminal,
                        "cost_usd": float(cost),
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "cost_complete": cost_complete,
                    },
                )
                await record(
                    session,
                    actor=Actor("SYSTEM", None),
                    action="run.finished",
                    case_id=case_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    detail={
                        "status": terminal,
                        "cost_usd": str(cost),
                        "cost_complete": cost_complete,
                    },
                )
                if settings.demo_mode and terminal == "DONE" and replay_key:
                    from darknetra.agent.replay import store

                    await store(session, case_id, run_id, replay_key, run.harness)
                await session.commit()
