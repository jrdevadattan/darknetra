"""Select usable, current extraction inputs while preserving old evidence/history."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.evidence.models import Evidence
from darknetra.extract.models import ExtractionRun, Observation


async def load_inputs(session: AsyncSession, case_id: UUID):
    evidence = {
        r.id: r
        for r in await session.scalars(
            select(Evidence).where(
                Evidence.case_id == case_id, Evidence.status.in_(["READY", "PARTIAL"])
            )
        )
    }
    runs = list(
        await session.scalars(
            select(ExtractionRun)
            .where(ExtractionRun.case_id == case_id, ExtractionRun.status == "DONE")
            .order_by(ExtractionRun.started_at.desc(), ExtractionRun.id)
        )
    )
    latest, allowed = set(), set()
    for run in runs:
        if run.evidence_id is None or run.evidence_id not in latest:
            allowed.add(run.id)
            if run.evidence_id:
                latest.add(run.evidence_id)
    observations = list(
        await session.scalars(
            select(Observation)
            .where(
                Observation.case_id == case_id,
                Observation.evidence_id.in_(evidence),
                Observation.run_id.in_(allowed),
                Observation.valid.is_(True),
            )
            .order_by(Observation.evidence_id, Observation.span_start, Observation.id)
        )
    )
    return evidence, observations
