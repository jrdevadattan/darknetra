"""Persisted event log is authoritative. Polling avoids replay/live subscription races."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from darknetra.agent.models import Run, RunEvent

TERMINAL = {"DONE", "ERROR", "CANCELLED", "BUDGET"}


async def append(
    session: AsyncSession, case_id: UUID, run_id: UUID, event_type: str, data: dict[str, Any]
) -> RunEvent:
    await session.execute(
        select(Run.id).where(Run.case_id == case_id, Run.id == run_id).with_for_update()
    )
    seq = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(RunEvent.seq), 0)).where(
                    RunEvent.case_id == case_id, RunEvent.run_id == run_id
                )
            )
            or 0
        )
        + 1
    )
    if event_type == "run.step":
        data = {**data, "seq": seq}
    if event_type == "activity.updated":
        from darknetra.api.v1.schemas.activity import ActivityUpdate

        data = ActivityUpdate.model_validate(
            {**data, "seq": seq, "at": datetime.now(UTC)}
        ).model_dump(mode="json")
    event = RunEvent(
        case_id=case_id, run_id=run_id, seq=seq, type=event_type, data=data, at=datetime.now(UTC)
    )
    session.add(event)
    await session.flush()
    return event


async def stream(
    factory: async_sessionmaker[AsyncSession], case_id: UUID, run_id: UUID, after: int = 0
) -> AsyncIterator[dict[str, str]]:
    while True:
        async with factory() as session:
            # Read status first: a terminal commit between these two reads must
            # either be included in rows or observed on the next polling pass.
            run = await session.scalar(select(Run).where(Run.case_id == case_id, Run.id == run_id))
            rows = list(
                (
                    await session.scalars(
                        select(RunEvent)
                        .where(
                            RunEvent.case_id == case_id,
                            RunEvent.run_id == run_id,
                            RunEvent.seq > after,
                        )
                        .order_by(RunEvent.seq)
                        .limit(200)
                    )
                ).all()
            )
            for event in rows:
                after = event.seq
                yield {
                    "id": str(event.seq),
                    "event": event.type,
                    "data": json.dumps(event.data, default=str),
                }
            if run is None or (run.status in TERMINAL and len(rows) < 200):
                # All terminal events are committed atomically with terminal state.
                return
        await asyncio.sleep(0.25)
