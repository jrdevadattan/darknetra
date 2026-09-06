import asyncio
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.pagination import page_rows
from darknetra.api.v1.schemas import admin as dto
from darknetra.api.v1.schemas import audit as audit_dto
from darknetra.api.v1.schemas.common import ActorRef, Page
from darknetra.audit.models import AuditEvent
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.models import Session, User
from darknetra.auth.passwords import hash_password
from darknetra.authz.deps import require, require_case
from darknetra.authz.permissions import Permission as P
from darknetra.db import get_session
from darknetra.errors import Conflict, NotFound, Validation
from darknetra.settings.models import Setting

router = APIRouter(tags=["admin"])


@router.post("/users", response_model=dto.User, status_code=201)
async def create_user(
    body: dto.UserCreate,
    actor: Actor = Depends(require(P.ADMIN_USERS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if await db.scalar(
        select(User.id).where(func.lower(User.username) == body.username.casefold())
    ):
        raise Conflict("Username already exists")
    user = User(
        id=uuid4(),
        username=body.username.casefold(),
        display_name=body.display_name,
        global_role=body.global_role,
        is_active=body.is_active,
        must_change_password=True,
        password_hash=await asyncio.to_thread(hash_password, body.password.get_secret_value()),
    )
    db.add(user)
    await db.flush()
    await record(db, actor=actor, action="user.create", target_type="user", target_id=user.id)
    await db.commit()
    return dto.User.model_validate(user)


@router.get("/users", response_model=Page[dto.User])
async def users(
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(require(P.ADMIN_USERS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    rows, next_cursor, total = await page_rows(db, select(User), User, cursor=cursor, limit=limit)
    return Page(
        items=[dto.User.model_validate(u) for u in rows], next_cursor=next_cursor, total=total
    )


@router.patch("/users/{id}", response_model=dto.User)
async def patch_user(
    id: UUID,
    body: dto.UserPatch,
    actor: Actor = Depends(require(P.ADMIN_USERS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    from datetime import UTC, datetime

    await db.execute(select(func.pg_advisory_xact_lock(1700000999)))
    user = await db.get(User, id)
    if not user:
        raise NotFound("Resource not found")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if user.global_role == "ADMIN" and (
        changes.get("global_role", "ADMIN") != "ADMIN" or changes.get("is_active") is False
    ):
        count = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.global_role == "ADMIN", User.is_active.is_(True))
        )
        if count <= 1:
            raise Conflict("At least one active administrator must remain")
    for key, value in changes.items():
        setattr(user, key, value)
    if "global_role" in changes or changes.get("is_active") is False:
        await db.execute(
            update(Session)
            .where(Session.user_id == id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    await record(
        db,
        actor=actor,
        action="user.update",
        target_type="user",
        target_id=id,
        detail={"fields": sorted(changes)},
    )
    await db.commit()
    return dto.User.model_validate(user)


def settings_dto(settings):
    return dto.Settings(
        demo_mode=settings.demo_mode,
        offline_mode=settings.offline_mode,
        monitor_interval_override=120 if settings.demo_mode else settings.monitor_interval_override,
        banner="SYNTHETIC DEMO" if settings.demo_mode else None,
        embedding_model=settings.embedding_model,
        case_lead_model=settings.case_lead_model,
        worker_model=settings.worker_model,
        offline_model=settings.offline_model,
    )


@router.get("/admin/settings", response_model=dto.Settings)
async def get_settings(request: Request, actor: Actor = Depends(require(P.ADMIN_SETTINGS))):
    return settings_dto(request.app.state.settings)


@router.patch("/admin/settings", response_model=dto.Settings)
async def patch_settings(
    body: dto.SettingsPatch,
    request: Request,
    actor: Actor = Depends(require(P.ADMIN_SETTINGS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None and key != "monitor_interval_override":
            continue
        row = await db.get(Setting, key)
        if not row:
            row = Setting(key=key, value=value, updated_by=actor.user_id)
            db.add(row)
        else:
            row.value, row.updated_by = value, actor.user_id
    await record(db, actor=actor, action="settings.update", detail={"fields": sorted(changes)})
    await db.commit()
    for key, value in changes.items():
        if value is not None or key == "monitor_interval_override":
            setattr(request.app.state.settings, key, value)
    return settings_dto(request.app.state.settings)


async def audit_page(db, statement, limit, cursor):
    rows, next_cursor, total = await page_rows(
        db, statement, AuditEvent, limit=limit, cursor=cursor, newest_by=AuditEvent.at
    )
    return Page(
        items=[
            audit_dto.AuditEvent(
                id=row.id,
                at=row.at,
                actor=ActorRef(kind=row.actor_kind, id=row.actor_id, display=row.actor_kind),
                case_id=row.case_id,
                thread_id=row.thread_id,
                action=row.action,
                target_type=row.target_type,
                target_id=row.target_id,
                detail=row.detail,
                result_hash=row.result_hash,
                request_id=row.request_id,
            )
            for row in rows
        ],
        next_cursor=next_cursor,
        total=total,
    )


def audit_filters(statement, action, actor_id, from_at, to_at):
    if any(value is not None and value.tzinfo is None for value in (from_at, to_at)):
        raise Validation("Audit dates require timezones")
    if from_at and to_at and from_at > to_at:
        raise Validation("Audit window starts after it ends")
    if action:
        statement = statement.where(AuditEvent.action == action)
    if actor_id:
        statement = statement.where(AuditEvent.actor_id == actor_id)
    if from_at:
        statement = statement.where(AuditEvent.at >= from_at)
    if to_at:
        statement = statement.where(AuditEvent.at <= to_at)
    return statement


@router.get("/audit", response_model=Page[audit_dto.AuditEvent])
async def global_audit(
    action: str | None = None,
    actor_id: UUID | None = None,
    from_at: datetime | None = Query(None, alias="from"),
    to_at: datetime | None = Query(None, alias="to"),
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(require(P.AUDIT_VIEW_GLOBAL)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    statement = audit_filters(select(AuditEvent), action, actor_id, from_at, to_at)
    return await audit_page(db, statement, limit, cursor)


@router.get("/cases/{case_id}/audit", response_model=Page[audit_dto.AuditEvent])
async def case_audit(
    action: str | None = None,
    actor_id: UUID | None = None,
    from_at: datetime | None = Query(None, alias="from"),
    to_at: datetime | None = Query(None, alias="to"),
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(P.AUDIT_VIEW_CASE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    statement = audit_filters(
        select(AuditEvent).where(AuditEvent.case_id == access[1].id),
        action,
        actor_id,
        from_at,
        to_at,
    )
    return await audit_page(db, statement, limit, cursor)
