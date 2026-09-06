"""Deterministic projection of durable activity events for a read-only execution graph."""

from pydantic import ValidationError
from sqlalchemy import func, select

from darknetra.agent.models import Run, RunEvent
from darknetra.api.v1.schemas.activity import (
    ActivityEdge,
    ActivityNode,
    ActivityUpdate,
    ExecutionSnapshot,
)
from darknetra.errors import NotFound

MAX_ACTIVITY_EVENTS = 10000
TERMINAL = {"DONE", "ERROR", "CANCELLED", "BUDGET"}


def project(
    run, rows, *, cursor: int, truncated: bool = False, cost_complete: bool | None = None
) -> ExecutionSnapshot:
    root = ActivityNode(
        id=run.id,
        kind="agent",
        label="Case lead",
        agent_role="CASE_LEAD",
        status={
            "QUEUED": "queued",
            "RUNNING": "running",
            "DONE": "completed",
            "ERROR": "failed",
            "CANCELLED": "cancelled",
            "BUDGET": "failed",
        }[run.status],
        phase="replay" if run.replayed_from_run_id else "working",
        summary="Replayed verified answer" if run.replayed_from_run_id else "Case run",
        seq=cursor,
    )
    nodes = {run.id: root}
    updates = []
    for row in rows:
        try:
            update = ActivityUpdate.model_validate({**row.data, "seq": row.seq, "at": row.at})
        except ValidationError:
            # Older/custom events cannot fabricate a valid graph. Surface incompleteness.
            truncated = True
            continue
        updates.append(update)
        nodes[update.id] = ActivityNode.model_validate(update.model_dump())
    # The authoritative run row wins over stale last activity, including after restart.
    if run.id in nodes:
        nodes[run.id].status = root.status
    if run.status in TERMINAL:
        for node in nodes.values():
            if node.id != run.id and node.status in {"queued", "running"}:
                node.status = "interrupted"
                node.terminal_inferred = True
                node.summary = "Run ended before this activity reported completion"
    return ExecutionSnapshot(
        case_id=run.case_id,
        thread_id=run.thread_id,
        run_id=run.id,
        run_status=run.status,
        cost_usd=float(getattr(run, "cost_usd", 0)),
        cost_complete=cost_complete,
        cursor=cursor,
        nodes=list(nodes.values()),
        edges=[
            ActivityEdge(source=n.parent_id, target=n.id)
            for n in nodes.values()
            if n.parent_id in nodes and n.parent_id != n.id
        ],
        events=updates,
        truncated=truncated,
        replayed_from_run_id=run.replayed_from_run_id,
    )


async def snapshot(db, case_id, thread_id, run_id) -> ExecutionSnapshot:
    # append() locks this same row: cursor, status and projection share one boundary.
    run = await db.scalar(
        select(Run)
        .where(Run.case_id == case_id, Run.thread_id == thread_id, Run.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise NotFound("Resource not found")
    cursor = int(
        await db.scalar(
            select(func.coalesce(func.max(RunEvent.seq), 0)).where(
                RunEvent.case_id == case_id, RunEvent.run_id == run_id
            )
        )
        or 0
    )
    rows = list(
        (
            await db.scalars(
                select(RunEvent)
                .where(
                    RunEvent.case_id == case_id,
                    RunEvent.run_id == run_id,
                    RunEvent.seq <= cursor,
                    RunEvent.type == "activity.updated",
                )
                .order_by(RunEvent.seq)
                .limit(MAX_ACTIVITY_EVENTS + 1)
            )
        ).all()
    )
    finished = await db.scalar(
        select(RunEvent)
        .where(
            RunEvent.case_id == case_id,
            RunEvent.run_id == run_id,
            RunEvent.seq <= cursor,
            RunEvent.type == "run.finished",
        )
        .order_by(RunEvent.seq.desc())
        .limit(1)
    )
    completeness = finished.data.get("cost_complete") if finished else None
    return project(
        run,
        rows[:MAX_ACTIVITY_EVENTS],
        cursor=cursor,
        truncated=len(rows) > MAX_ACTIVITY_EVENTS,
        cost_complete=completeness if isinstance(completeness, bool) else None,
    )
