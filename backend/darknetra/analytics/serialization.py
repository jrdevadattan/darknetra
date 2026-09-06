"""Frozen API DTOs assembled only from same-case store records."""

from sqlalchemy import select

from darknetra.api.v1.schemas import analytics as dto
from darknetra.api.v1.schemas.common import EvidenceRef
from darknetra.api.v1.schemas.entities import Entity
from darknetra.decisions.service import decision_dto, latest_decision
from darknetra.errors import NotFound
from darknetra.evidence.models import Evidence
from darknetra.extract.models import CanonicalEntity


def entity_dto(row):
    return Entity(
        id=row.id,
        type=row.type,
        value=row.value,
        display=row.display,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        observation_count=row.observation_count,
        sample_spans=[],
    )


async def feature_dtos(session, case_id, features):
    ids = {eid for feature in features for eid in feature.get("evidence_ids", [])}
    evidence = {
        str(e.id): EvidenceRef(id=e.id, code=e.code)
        for e in await session.scalars(
            select(Evidence).where(Evidence.case_id == case_id, Evidence.id.in_(ids))
        )
    }
    return [
        dto.FeatureContribution(
            name=f["name"],
            family=f["family"],
            value=f["value"],
            weight=f["weight"],
            contribution=f["contribution"],
            explanation=f["explanation"],
            evidence=[
                evidence[str(eid)] for eid in f.get("evidence_ids", []) if str(eid) in evidence
            ],
        )
        for f in features
    ]


async def link_dto(session, row):
    entities = {
        e.id: e
        for e in await session.scalars(
            select(CanonicalEntity).where(
                CanonicalEntity.case_id == row.case_id,
                CanonicalEntity.id.in_([row.subject_a_id, row.subject_b_id]),
            )
        )
    }
    if len(entities) != 2:
        raise NotFound("Candidate entities not found")
    decision = await latest_decision(session, row.case_id, "LINK", row.id, row.version)
    return dto.LinkCandidate(
        id=row.id,
        subject_a=entity_dto(entities[row.subject_a_id]),
        subject_b=entity_dto(entities[row.subject_b_id]),
        score=row.score,
        band=row.band,
        families=row.families,
        features=await feature_dtos(session, row.case_id, row.features),
        contradictions=row.contradictions,
        status=row.status,
        version=row.version,
        supersedes_id=row.supersedes_id,
        decision=await decision_dto(session, decision) if decision else None,
        run_id=row.run_id,
        rescored=bool(row.meta.get("rescored")),
    )


async def activity_dto(session, row):
    evidence = await session.scalar(
        select(Evidence).where(Evidence.case_id == row.case_id, Evidence.id == row.evidence_id)
    )
    if evidence is None:
        raise NotFound("Evidence not found")
    return dto.ActivityCandidate(
        id=row.id,
        evidence=EvidenceRef(id=evidence.id, code=evidence.code),
        score=row.score,
        label=row.label,
        features=await feature_dtos(session, row.case_id, row.features),
        status=row.status,
    )


async def wallet_dto(session, row):
    evidence = None
    if row.live_summary_evidence_id:
        evidence = await session.scalar(
            select(Evidence).where(
                Evidence.case_id == row.case_id, Evidence.id == row.live_summary_evidence_id
            )
        )
    return dto.WalletAssessment(
        id=row.id,
        address=row.address,
        chain=row.chain,
        gnn=row.gnn,
        gnn_unavailable_reason=row.gnn_unavailable_reason,
        sanctions=row.sanctions,
        live_summary=row.live_summary,
        live_summary_evidence=EvidenceRef(id=evidence.id, code=evidence.code) if evidence else None,
        tags=row.tags,
        traceable=row.traceable,
        assessed_at=row.assessed_at,
        version=row.version,
    )
