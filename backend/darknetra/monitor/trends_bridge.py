"""Promote deterministic current trend candidates with evidence and a seven-day dedupe."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from darknetra.analytics.trends import candidates
from darknetra.cases.models import Case
from darknetra.cases.service import ensure_open
from darknetra.evidence.models import Evidence
from darknetra.extract.models import Observation
from darknetra.monitor.alerts import raise_alert
from darknetra.monitor.models import Alert


async def promote_candidates(db, *, case, actor):
    case = await db.scalar(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ensure_open(case)
    now = datetime.now(UTC)
    trends = await candidates(db, case.id)
    created = []
    for series in trends.series:
        point = series.points[-1] if series.points else None
        if (
            not series.candidate
            or point is None
            or (point.z or 0) < 3
            or point.count < 3
            or point.unique_sources + point.unique_aliases < 3
        ):
            continue
        term_hash = hashlib.sha256((series.type + ":" + series.term).encode()).hexdigest()
        previous = await db.scalar(
            select(Alert.id).where(
                Alert.case_id == case.id,
                Alert.kind == "TREND",
                Alert.at >= now - timedelta(days=7),
                Alert.diversity["term_hash"].astext == term_hash,
            )
        )
        if previous:
            continue
        evidence_ids = list(
            await db.scalars(
                select(Observation.evidence_id)
                .join(
                    Evidence,
                    (Evidence.id == Observation.evidence_id)
                    & (Evidence.case_id == Observation.case_id),
                )
                .where(
                    Observation.case_id == case.id,
                    Observation.type == series.type,
                    Observation.normalized["value"].astext == series.term,
                    Evidence.status.in_(["READY", "PARTIAL"]),
                    Evidence.source_class.in_(case.source_policy["allowed_source_classes"]),
                )
                .distinct()
            )
        )
        if not evidence_ids:
            continue
        created.append(
            await raise_alert(
                db,
                case_id=case.id,
                actor=actor,
                kind="TREND",
                title="Observed frequency requires review",
                summary=f"Stored observations of {series.term} meet the current deterministic trend count, z-score and diversity gates; this is a review signal.",
                evidence_ids=evidence_ids,
                diversity={
                    "term_hash": term_hash,
                    "z_score": point.z,
                    "count": point.count,
                    "unique_sources": point.unique_sources,
                    "unique_aliases": point.unique_aliases,
                    "day": point.day.isoformat(),
                },
                config_version="trend-v1",
            )
        )
    return created
