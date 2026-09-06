"""Current observations from accessible evidence, selected with explicit case bounds."""

from uuid import UUID

from sqlalchemy import Select, exists, select, tuple_
from sqlalchemy.orm import aliased

from darknetra.evidence.models import Derivative, Evidence
from darknetra.extract.models import ExtractionRun, Observation


def current_observations(case_id: UUID) -> Select[tuple[Observation]]:
    newer = aliased(ExtractionRun)
    newer_run = exists(
        select(newer.id)
        .where(
            newer.case_id == case_id,
            newer.status == "DONE",
            newer.evidence_id.is_not_distinct_from(ExtractionRun.evidence_id),
            tuple_(newer.started_at, newer.id) > tuple_(ExtractionRun.started_at, ExtractionRun.id),
        )
        .correlate(ExtractionRun)
    )
    return (
        select(Observation)
        .join(
            Evidence,
            (Evidence.case_id == Observation.case_id) & (Evidence.id == Observation.evidence_id),
        )
        .join(
            ExtractionRun,
            (ExtractionRun.case_id == Observation.case_id)
            & (ExtractionRun.id == Observation.run_id),
        )
        .join(
            Derivative,
            (Derivative.case_id == Observation.case_id)
            & (Derivative.id == Observation.derivative_id),
        )
        .where(
            Observation.case_id == case_id,
            Evidence.case_id == case_id,
            ExtractionRun.case_id == case_id,
            Derivative.case_id == case_id,
            Evidence.status.in_(["READY", "PARTIAL"]),
            Derivative.status == "READY",
            ExtractionRun.status == "DONE",
            ~newer_run,
        )
    )
