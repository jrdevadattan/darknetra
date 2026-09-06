from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import alerts as dto
from darknetra.api.v1.schemas.common import AlertKind, AlertStatus, Page, Rationale
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.errors import Validation
from darknetra.monitor.alerts import alert_dto, changes_since, handle
from darknetra.monitor.models import Alert

router = APIRouter(tags=["alerts"])


@router.get("/cases/{case_id}/alerts", response_model=Page[dto.Alert])
async def list_alerts(
    case_id: UUID,
    status: AlertStatus | None = None,
    kind: AlertKind | None = None,
    item_id: UUID | None = None,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(Permission.ALERT_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(Alert).where(Alert.case_id == case_id)
    for column, value in [(Alert.status, status), (Alert.kind, kind), (Alert.item_id, item_id)]:
        if value is not None:
            query = query.where(column == value)
    if cursor:
        query = query.where(Alert.id > cursor)
    rows = list(await db.scalars(query.order_by(Alert.id).limit(limit + 1)))
    return Page(
        items=[await alert_dto(db, row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


def expected(header):
    if header is None:
        return None
    try:
        return int(header.strip('"'))
    except ValueError:
        raise Validation("If-Match must contain the alert version") from None


@router.post("/cases/{case_id}/alerts/{aid}/ack", response_model=dto.Alert)
async def ack(
    case_id: UUID,
    aid: UUID,
    body: Rationale,
    if_match: str | None = Header(None),
    access=Depends(require_case(Permission.ALERT_HANDLE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    alert, _ = await handle(
        db,
        case=access[1],
        actor=access[0],
        aid=aid,
        action="ack",
        rationale=body.rationale,
        expected_version=expected(if_match),
    )
    await db.commit()
    return alert


@router.post("/cases/{case_id}/alerts/{aid}/dismiss", response_model=dto.Alert)
async def dismiss(
    case_id: UUID,
    aid: UUID,
    body: Rationale,
    if_match: str | None = Header(None),
    access=Depends(require_case(Permission.ALERT_HANDLE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    alert, _ = await handle(
        db,
        case=access[1],
        actor=access[0],
        aid=aid,
        action="dismiss",
        rationale=body.rationale,
        expected_version=expected(if_match),
    )
    await db.commit()
    return alert


@router.post("/cases/{case_id}/alerts/{aid}/escalate", response_model=dto.EscalateResult)
async def escalate(
    case_id: UUID,
    aid: UUID,
    body: Rationale,
    if_match: str | None = Header(None),
    access=Depends(require_case(Permission.ALERT_HANDLE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    alert, finding = await handle(
        db,
        case=access[1],
        actor=access[0],
        aid=aid,
        action="escalate",
        rationale=body.rationale,
        expected_version=expected(if_match),
    )
    await db.commit()
    return dto.EscalateResult(alert=alert, finding=finding)


@router.get("/cases/{case_id}/changes", response_model=dto.Changes)
async def changes(
    case_id: UUID,
    since: datetime,
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await changes_since(db, case_id, since)
