from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from darknetra.analytics import correlate, graph, trends, wallets
from darknetra.analytics.models import ActivityCandidate, LinkCandidate, WalletAssessment
from darknetra.analytics.serialization import activity_dto, link_dto, wallet_dto
from darknetra.api.v1.schemas import analytics as dto
from darknetra.api.v1.schemas.cases import LedgerImportResult
from darknetra.api.v1.schemas.common import Band, CandidateStatus, Page
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission as P
from darknetra.db import get_session
from darknetra.errors import NotFound

router = APIRouter(tags=["analytics"])


@router.post("/cases/{case_id}/ledger/import", response_model=LedgerImportResult)
async def ledger_import(
    case_id: UUID,
    request: Request,
    nodes: UploadFile = File(...),
    edges: UploadFile = File(...),
    address_map: UploadFile = File(...),
    access=Depends(require_case(P.CASE_EDIT)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    from darknetra.analytics.ledger import MAX_FILE_BYTES, import_ledger

    result = await import_ledger(
        db,
        case=access[1],
        actor=access[0],
        nodes=await nodes.read(MAX_FILE_BYTES + 1),
        edges=await edges.read(MAX_FILE_BYTES + 1),
        address_map=await address_map.read(MAX_FILE_BYTES + 1),
        settings=request.app.state.settings,
        request_id=request.state.request_id,
    )
    await db.commit()
    return result


@router.post("/cases/{case_id}/analytics/correlate", response_model=dto.CorrelateResult)
async def run_correlation(
    case_id: UUID,
    data: dto.CorrelateRequest,
    request: Request,
    access=Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    run = await correlate.run_case(
        db,
        case_id,
        access[0],
        request.app.state.settings,
        data.focus_entity_id,
        request_id=request.state.request_id,
    )
    result = dto.CorrelateResult(
        run_id=run.id,
        candidates_created=run.stats["candidates_created"],
        candidates_rescored=run.stats["candidates_rescored"],
    )
    await db.commit()
    return result


@router.get("/cases/{case_id}/analytics/links", response_model=Page[dto.LinkCandidate])
async def links(
    case_id: UUID,
    band: Band | None = None,
    status: CandidateStatus | None = None,
    entity_id: UUID | None = None,
    min_score: int = Query(0, ge=0, le=100),
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    stmt = graph.latest_links(case_id).where(LinkCandidate.score >= min_score)
    if band:
        stmt = stmt.where(LinkCandidate.band == band)
    if status:
        stmt = stmt.where(LinkCandidate.status == status)
    if entity_id:
        stmt = stmt.where(
            or_(LinkCandidate.subject_a_id == entity_id, LinkCandidate.subject_b_id == entity_id)
        )
    if cursor:
        stmt = stmt.where(LinkCandidate.id > cursor)
    rows = list(await db.scalars(stmt.order_by(LinkCandidate.id).limit(limit + 1)))
    return Page(
        items=[await link_dto(db, row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/cases/{case_id}/analytics/links/{candidate_id}", response_model=dto.LinkCandidate)
async def link_detail(
    case_id: UUID,
    candidate_id: UUID,
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await db.scalar(
        select(LinkCandidate).where(
            LinkCandidate.case_id == case_id, LinkCandidate.id == candidate_id
        )
    )
    if row is None:
        raise NotFound("Resource not found")
    return await link_dto(db, row)


@router.get("/cases/{case_id}/analytics/activity", response_model=Page[dto.ActivityCandidate])
async def activity(
    case_id: UUID,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    newer = aliased(ActivityCandidate)
    stmt = select(ActivityCandidate).where(
        ActivityCandidate.case_id == case_id,
        ~exists(
            select(newer.id).where(
                newer.case_id == case_id,
                newer.evidence_id == ActivityCandidate.evidence_id,
                newer.version > ActivityCandidate.version,
            )
        ),
    )
    if cursor:
        stmt = stmt.where(ActivityCandidate.id > cursor)
    rows = list(await db.scalars(stmt.order_by(ActivityCandidate.id).limit(limit + 1)))
    return Page(
        items=[await activity_dto(db, row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/cases/{case_id}/graph", response_model=dto.GraphDTO)
async def graph_panel(
    case_id: UUID,
    focus: UUID | None = None,
    depth: int = Query(1, ge=0, le=2),
    include_pending: bool = True,
    include_rejected: bool = False,
    include_evidence: bool = False,
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await graph.query(
        db, case_id, focus, depth, include_pending, include_rejected, include_evidence
    )


@router.get("/cases/{case_id}/graph/edges/{edge_id}/provenance", response_model=dto.EdgeProvenance)
async def edge_provenance(
    case_id: UUID,
    edge_id: UUID,
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await graph.provenance(db, case_id, edge_id, access[0])


@router.post("/cases/{case_id}/wallets/assess", response_model=dto.WalletAssessment)
async def assess_wallet(
    case_id: UUID,
    data: dto.WalletAssessRequest,
    request: Request,
    access=Depends(require_case(P.THREAD_RUN)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await wallets.assess_wallet(db, access[1], access[0], data, request.app.state.settings)
    result = await wallet_dto(db, row)
    await db.commit()
    return result


@router.get("/cases/{case_id}/wallets", response_model=Page[dto.WalletAssessment])
async def wallet_list(
    case_id: UUID,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    stmt = select(WalletAssessment).where(WalletAssessment.case_id == case_id)
    if cursor:
        stmt = stmt.where(WalletAssessment.id > cursor)
    rows = list(await db.scalars(stmt.order_by(WalletAssessment.id).limit(limit + 1)))
    return Page(
        items=[await wallet_dto(db, row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/cases/{case_id}/trends", response_model=dto.Trends)
async def trend_series(
    case_id: UUID,
    window_days: int = Query(30, ge=1, le=366),
    term: str | None = None,
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    buckets = await trends.compute_buckets(db, case_id, window_days, persist=False)
    return await trends.candidates(db, case_id, window_days, term, buckets)
