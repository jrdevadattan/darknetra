from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import entities as dto
from darknetra.api.v1.schemas.common import Page
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.errors import Conflict, NotFound
from darknetra.evidence.models import Evidence
from darknetra.evidence.service import get_derivative_text, get_evidence
from darknetra.extract.models import CanonicalEntity, ExtractionRun, Observation
from darknetra.extract.pipeline import run_evidence
from darknetra.extract.visibility import current_observations

router = APIRouter(tags=["entities"])


async def observation_dto(db, observation):
    if not await db.scalar(
        current_observations(observation.case_id)
        .with_only_columns(Observation.id)
        .where(Observation.id == observation.id)
    ):
        raise NotFound("Observation not found")
    evidence = await get_evidence(db, observation.case_id, observation.evidence_id)
    return dto.Observation(
        id=observation.id,
        type=observation.type,
        raw=observation.raw,
        normalized=observation.normalized,
        evidence={"id": evidence.id, "code": evidence.code},
        span={
            "start": observation.span_start,
            "end": observation.span_end,
            "line": observation.line_no,
        },
        validator=observation.validator,
        valid=observation.valid,
        confidence=observation.confidence,
        canonical_entity_id=observation.canonical_entity_id,
        run_id=observation.run_id,
        meta=observation.meta,
    )


async def entity_dto(db, entity):
    available = current_observations(entity.case_id).where(
        Observation.canonical_entity_id == entity.id
    )
    count, first_seen, last_seen = (
        await db.execute(
            available.with_only_columns(
                func.count(Observation.id),
                func.min(Evidence.captured_at),
                func.max(Evidence.captured_at),
            )
        )
    ).one()
    if not count:
        raise NotFound("Entity not found")
    rows = await db.scalars(
        available.order_by(Observation.evidence_id, Observation.span_start, Observation.id).limit(3)
    )
    spans = []
    for row in rows:
        obs = await observation_dto(db, row)
        spans.append(dto.SampleSpan(evidence=obs.evidence, span=obs.span, snippet=obs.raw[:240]))
    return dto.Entity(
        id=entity.id,
        type=entity.type,
        value=entity.value,
        display=entity.display,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        observation_count=count,
        sample_spans=spans,
    )


@router.get("/cases/{case_id}/entities", response_model=Page[dto.Entity])
async def entities(
    case_id: UUID,
    type: str | None = None,
    q: str | None = None,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    available = current_observations(case_id).with_only_columns(Observation.canonical_entity_id)
    stmt = select(CanonicalEntity).where(
        CanonicalEntity.case_id == case_id, CanonicalEntity.id.in_(available)
    )
    if type:
        stmt = stmt.where(CanonicalEntity.type == type)
    if q:
        stmt = stmt.where(CanonicalEntity.value.ilike("%" + q + "%"))
    if cursor:
        stmt = stmt.where(CanonicalEntity.id > cursor)
    rows = list(await db.scalars(stmt.order_by(CanonicalEntity.id).limit(limit + 1)))
    return Page(
        items=[await entity_dto(db, row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/cases/{case_id}/entities/{entity_id}")
async def entity_detail(
    case_id: UUID,
    entity_id: UUID,
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    entity = await db.scalar(
        select(CanonicalEntity).where(
            CanonicalEntity.case_id == case_id, CanonicalEntity.id == entity_id
        )
    )
    if not entity:
        raise NotFound("Entity not found")
    observations = await db.scalars(
        current_observations(case_id).where(Observation.canonical_entity_id == entity_id).limit(200)
    )
    return {
        "entity": await entity_dto(db, entity),
        "observations": [await observation_dto(db, row) for row in observations],
        "edges": [],
    }


@router.get("/cases/{case_id}/observations/{obs_id}", response_model=dto.ObservationDetail)
async def observation_detail(
    case_id: UUID,
    obs_id: UUID,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await db.scalar(current_observations(case_id).where(Observation.id == obs_id))
    if not row:
        raise NotFound("Observation not found")
    result = await observation_dto(db, row)
    text = await get_derivative_text(
        db, case_id, row.evidence_id, row.derivative_id, request.app.state.settings
    )
    return dto.ObservationDetail(
        **result.model_dump(),
        context={
            "evidence": result.evidence,
            "span": result.span,
            "text": row.raw,
            "before": text[max(0, row.span_start - 200) : row.span_start],
            "after": text[row.span_end : row.span_end + 200],
            "line_no": row.line_no,
        },
    )


@router.post("/cases/{case_id}/extraction/run", response_model=list[dto.ExtractionRun])
async def extract(
    case_id: UUID,
    body: dto.ExtractionRequest,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_UPLOAD)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if access[1].status != "OPEN":
        raise Conflict("Case is not open")
    stmt = select(Evidence.id).where(
        Evidence.case_id == case_id, Evidence.status.in_(["READY", "PARTIAL"])
    )
    if body.evidence_id:
        await get_evidence(db, case_id, body.evidence_id)
        stmt = stmt.where(Evidence.id == body.evidence_id)
    results = []
    for eid in await db.scalars(stmt):
        try:
            results.append(
                dto.ExtractionRun.model_validate(
                    await run_evidence(db, case_id, eid, request.app.state.settings)
                )
            )
        except NotFound:
            continue
    from darknetra.extract.novel_terms import discover

    await discover(db, case_id, request.app.state.settings)
    await db.commit()
    return results


@router.get("/cases/{case_id}/extraction/runs", response_model=Page[dto.ExtractionRun])
async def runs(
    case_id: UUID,
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    rows = await db.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.case_id == case_id)
        .order_by(ExtractionRun.started_at.desc())
        .limit(200)
    )
    return Page(items=[dto.ExtractionRun.model_validate(row) for row in rows])
