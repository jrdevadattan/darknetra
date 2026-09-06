from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import watchlists as dto
from darknetra.api.v1.schemas.alerts import Alert as AlertResponse
from darknetra.api.v1.schemas.common import Page
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.errors import RateLimited
from darknetra.evidence.models import Evidence
from darknetra.monitor import service
from darknetra.monitor.models import MonitorHit, MonitorRun, Watchlist, WatchlistItem
from darknetra.monitor.runner import run_item

router = APIRouter(tags=["watchlists"])


@router.post("/cases/{case_id}/monitor/trends", response_model=Page[AlertResponse])
async def run_trends(
    case_id: UUID,
    access=Depends(require_case(Permission.WATCHLIST_MANAGE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    from darknetra.monitor.alerts import alert_dto
    from darknetra.monitor.trends_bridge import promote_candidates

    rows = await promote_candidates(db, case=access[1], actor=access[0])
    result = Page(items=[await alert_dto(db, row) for row in rows])
    await db.commit()
    return result


@router.post("/cases/{case_id}/watchlists", response_model=dto.Watchlist, status_code=201)
async def create_watchlist(
    case_id: UUID,
    body: dto.WatchlistCreate,
    access=Depends(require_case(Permission.WATCHLIST_MANAGE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    result = await service.watchlist_dto(
        db, await service.create_watchlist(db, access[1], access[0], body.name)
    )
    await db.commit()
    return result


@router.get("/cases/{case_id}/watchlists", response_model=Page[dto.Watchlist])
async def list_watchlists(
    case_id: UUID,
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    rows = await db.scalars(
        select(Watchlist)
        .where(Watchlist.case_id == case_id)
        .order_by(Watchlist.created_at, Watchlist.id)
    )
    return Page(items=[await service.watchlist_dto(db, row) for row in rows])


@router.post(
    "/cases/{case_id}/watchlists/{wid}/items", response_model=dto.WatchlistItem, status_code=201
)
async def create_item(
    case_id: UUID,
    wid: UUID,
    body: dto.WatchlistItemIn,
    request: Request,
    access=Depends(require_case(Permission.WATCHLIST_MANAGE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await service.create_item(db, access[1], wid, access[0], body, request.app.state.settings)
    await db.commit()
    return row


@router.get("/cases/{case_id}/watchlists/{wid}/items", response_model=Page[dto.WatchlistItem])
async def list_items(
    case_id: UUID,
    wid: UUID,
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.get_watchlist(db, case_id, wid)
    rows = await db.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.case_id == case_id, WatchlistItem.watchlist_id == wid)
        .order_by(WatchlistItem.created_at, WatchlistItem.id)
    )
    return Page(items=list(rows))


@router.patch("/cases/{case_id}/watchlists/{wid}/items/{iid}", response_model=dto.WatchlistItem)
async def patch_item(
    case_id: UUID,
    wid: UUID,
    iid: UUID,
    body: dto.WatchlistItemPatch,
    request: Request,
    access=Depends(require_case(Permission.WATCHLIST_MANAGE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await service.patch_item(
        db, access[1], wid, iid, access[0], body, request.app.state.settings
    )
    await db.commit()
    return row


@router.delete("/cases/{case_id}/watchlists/{wid}/items/{iid}", response_model=dto.WatchlistItem)
async def deactivate(
    case_id: UUID,
    wid: UUID,
    iid: UUID,
    request: Request,
    access=Depends(require_case(Permission.WATCHLIST_MANAGE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await service.patch_item(
        db,
        access[1],
        wid,
        iid,
        access[0],
        dto.WatchlistItemPatch(active=False),
        request.app.state.settings,
    )
    await db.commit()
    return row


@router.post("/cases/{case_id}/watchlists/{wid}/items/{iid}/run", response_model=dto.MonitorRun)
async def run_now(
    case_id: UUID,
    wid: UUID,
    iid: UUID,
    request: Request,
    access=Depends(require_case(Permission.WATCHLIST_MANAGE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.get_item(db, case_id, wid, iid)
    row = await run_item(
        db,
        case_id=case_id,
        item_id=iid,
        actor=access[0],
        settings=request.app.state.settings,
        session_factory=request.app.state.session_factory,
        manual=True,
    )
    if row.status == "RATE_LIMITED":
        await db.commit()
        raise RateLimited(
            "Monitoring sources are rate limited",
            detail={"run_id": str(row.id), "errors": row.errors},
        )
    await db.commit()
    return row


@router.get("/cases/{case_id}/monitor/runs", response_model=Page[dto.MonitorRun])
async def runs(
    case_id: UUID,
    item_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(MonitorRun).where(MonitorRun.case_id == case_id)
    if item_id:
        query = query.where(MonitorRun.item_id == item_id)
    if cursor:
        query = query.where(MonitorRun.id > cursor)
    rows = list(await db.scalars(query.order_by(MonitorRun.id).limit(limit + 1)))
    return Page(
        items=rows[:limit], next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None
    )


@router.get("/cases/{case_id}/monitor/hits", response_model=Page[dto.MonitorHit])
async def hits(
    case_id: UUID,
    item_id: UUID | None = None,
    alertable: bool | None = None,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(MonitorHit).where(MonitorHit.case_id == case_id)
    if item_id:
        query = query.where(MonitorHit.item_id == item_id)
    if alertable is not None:
        query = query.where(MonitorHit.alertable == alertable)
    if cursor:
        query = query.where(MonitorHit.id > cursor)
    rows = list(await db.scalars(query.order_by(MonitorHit.id).limit(limit + 1)))
    output = []
    for row in rows[:limit]:
        evidence = (
            await db.scalar(
                select(Evidence).where(Evidence.case_id == case_id, Evidence.id == row.evidence_id)
            )
            if row.evidence_id
            else None
        )
        output.append(
            dto.MonitorHit(
                id=row.id,
                item_id=row.item_id,
                evidence={"id": evidence.id, "code": evidence.code} if evidence else None,
                relevance=row.relevance,
                alertable=row.alertable,
                reasons=row.reasons,
                alert_id=row.alert_id,
                at=row.at,
            )
        )
    return Page(items=output, next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)
