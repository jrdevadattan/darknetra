from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import findings as dto
from darknetra.api.v1.schemas.common import DecisionTarget, FindingKind, FindingStatus, Page
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission as P
from darknetra.db import get_session
from darknetra.decisions import service
from darknetra.decisions.models import Decision, Finding
from darknetra.errors import Validation

router = APIRouter(tags=["findings", "decisions"])


def expected_version(if_match):
    if if_match is None:
        return None
    try:
        value = int(if_match.strip('"'))
    except ValueError as exc:
        raise Validation("If-Match must contain a positive target version") from exc
    if value < 1:
        raise Validation("If-Match must contain a positive target version")
    return value


@router.post("/cases/{case_id}/decisions", response_model=dto.Decision, status_code=201)
async def create_decision(
    case_id: UUID,
    data: dto.DecisionCreate,
    request: Request,
    if_match: Annotated[str | None, Header()] = None,
    access=Depends(require_case(P.DECIDE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await service.decide(
        db,
        case=access[1],
        actor=access[0],
        **data.model_dump(),
        target_version=expected_version(if_match),
        request_id=request.state.request_id,
    )
    result = await service.decision_dto(db, row)
    await db.commit()
    return result


@router.get("/cases/{case_id}/decisions", response_model=Page[dto.Decision])
async def decisions(
    case_id: UUID,
    target_type: DecisionTarget | None = None,
    target_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(Decision).where(Decision.case_id == case_id)
    if target_type:
        query = query.where(Decision.target_type == target_type)
    if target_id:
        query = query.where(Decision.target_id == target_id)
    if cursor:
        query = query.where(Decision.id > cursor)
    rows = list(await db.scalars(query.order_by(Decision.id).limit(limit + 1)))
    return Page(
        items=[await service.decision_dto(db, r) for r in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.post("/cases/{case_id}/findings", response_model=dto.Finding, status_code=201)
async def create_finding(
    case_id: UUID,
    data: dto.FindingCreate,
    request: Request,
    access=Depends(require_case(P.FINDING_EDIT)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await service.create_finding(
        db, case=access[1], actor=access[0], data=data, request_id=request.state.request_id
    )
    result = await service.finding_dto(db, row)
    await db.commit()
    return result


@router.get("/cases/{case_id}/findings", response_model=Page[dto.Finding])
async def findings(
    case_id: UUID,
    status: FindingStatus | None = None,
    kind: FindingKind | None = None,
    thread_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(Finding).where(Finding.case_id == case_id)
    if status:
        query = query.where(Finding.status == status)
    if kind:
        query = query.where(Finding.kind == kind)
    if thread_id:
        query = query.where(Finding.thread_id == thread_id)
    if cursor:
        query = query.where(Finding.id > cursor)
    rows = list(await db.scalars(query.order_by(Finding.id).limit(limit + 1)))
    return Page(
        items=[await service.finding_dto(db, r) for r in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.post("/cases/{case_id}/findings/{fid}/promote", response_model=dto.Finding)
async def promote(
    case_id: UUID,
    fid: UUID,
    data: dto.PromoteRequest | dto.DecisionCreate,
    request: Request,
    access=Depends(require_case(P.DECIDE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if isinstance(data, dto.DecisionCreate):
        if data.target_type != "FINDING" or data.target_id != fid or data.decision != "ACCEPT":
            raise Validation("Inline promotion must accept this finding")
        decision = await service.decide(
            db,
            case=access[1],
            actor=access[0],
            **data.model_dump(),
            request_id=request.state.request_id,
        )
        decision_id = decision.id
    else:
        decision_id = data.decision_id
    row = await service.promote(
        db,
        case=access[1],
        actor=access[0],
        finding_id=fid,
        decision_id=decision_id,
        request_id=request.state.request_id,
    )
    result = await service.finding_dto(db, row)
    await db.commit()
    return result
