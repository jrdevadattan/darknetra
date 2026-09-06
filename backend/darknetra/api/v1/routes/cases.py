from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.pagination import page_rows
from darknetra.api.v1.schemas import cases as dto
from darknetra.api.v1.schemas.common import ActorRef, Page, Reason, ResourceRef
from darknetra.audit.models import AuditEvent
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.authz.deps import current_actor, require, require_case
from darknetra.authz.permissions import Permission as P
from darknetra.authz.permissions import permitted, scope_permits
from darknetra.cases import service
from darknetra.cases.models import Case, CaseMembership
from darknetra.crypto.fields import FieldCipher
from darknetra.db import get_session
from darknetra.errors import Conflict, Forbidden, NotFound, Validation

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=dto.Case, status_code=201)
async def create_case(
    body: dto.CaseCreate,
    request: Request,
    actor: Actor = Depends(require(P.CASE_CREATE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    case = await service.create(db, actor, body, request.app.state.settings)
    result = await service.case_dto(db, case, actor)
    await db.commit()
    return result


@router.get("/cases", response_model=Page[dto.Case])
async def list_cases(
    status: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if actor.kind == "TOKEN" and not scope_permits(actor.scopes, P.CASE_VIEW):
        raise Forbidden("Permission denied")
    statement = select(Case)
    if actor.global_role != "ADMIN":
        statement = statement.join(CaseMembership).where(CaseMembership.user_id == actor.user_id)
    if actor.token_case_id:
        statement = statement.where(Case.id == actor.token_case_id)
    if status:
        statement = statement.where(Case.status == status)
    if q:
        statement = statement.where(Case.title.ilike(f"%{q[:200]}%"))
    rows, next_cursor, total = await page_rows(db, statement, Case, cursor=cursor, limit=limit)
    return Page(
        items=[await service.case_dto(db, row, actor) for row in rows],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/cases/{case_id}", response_model=dto.Case)
async def get_case(
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    return await service.case_dto(db, case, actor)


@router.patch("/cases/{case_id}", response_model=dto.Case)
async def patch_case(
    body: dto.CasePatch,
    request: Request,
    access=Depends(require_case(P.CASE_EDIT)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    service.ensure_open(case)
    changes = body.model_dump(exclude_unset=True)
    if "source_policy" in changes and not permitted(
        actor.global_role, request.state.case_role, P.CASE_MANAGE_POLICY
    ):
        raise Forbidden("Permission denied")
    if (
        "legal_hold" in changes
        and actor.global_role != "ADMIN"
        and request.state.case_role != "OWNER"
    ):
        raise Forbidden("Only the case owner may change legal hold")
    if "title" in changes and (not body.title or not body.title.strip()):
        raise Validation("Title cannot be empty")
    cipher = FieldCipher(request.app.state.settings.field_key)
    for field in ("title", "scope_notes", "legal_hold"):
        if field in changes:
            if field == "legal_hold" and changes[field] is None:
                raise Validation("Legal hold must be a boolean")
            setattr(case, field, changes[field])
    if "source_policy" in changes:
        if body.source_policy is None:
            raise Validation("Source policy cannot be null")
        case.source_policy = body.source_policy.model_dump()
    if "authority_ref" in changes:
        case.authority_ref_enc = (
            cipher.encrypt(body.authority_ref, "cases:authority_ref")
            if body.authority_ref
            else None
        )
        case.authority_ref_bidx = (
            cipher.blind_index(body.authority_ref) if body.authority_ref else None
        )
    await record(
        db,
        actor=actor,
        case_id=case.id,
        action="case.update",
        target_type="case",
        target_id=case.id,
        detail={"fields": sorted(changes)},
    )
    result = await service.case_dto(db, case, actor)
    await db.commit()
    return result


@router.post("/cases/{case_id}/close", response_model=dto.Case)
async def close_case(
    body: Reason,
    access=Depends(require_case(P.CASE_CLOSE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    case = await service.transition(db, case, actor, "CLOSED", body.reason)
    result = await service.case_dto(db, case, actor)
    await db.commit()
    return result


@router.post("/cases/{case_id}/reopen", response_model=dto.Case)
async def reopen_case(
    body: Reason,
    access=Depends(require_case(P.CASE_CLOSE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    case = await service.transition(db, case, actor, "OPEN", body.reason)
    result = await service.case_dto(db, case, actor)
    await db.commit()
    return result


@router.post("/cases/{case_id}/archive", response_model=dto.Case)
async def archive_case(
    body: Reason,
    access=Depends(require_case(P.CASE_ARCHIVE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    case = await service.transition(db, case, actor, "ARCHIVED", body.reason)
    result = await service.case_dto(db, case, actor)
    await db.commit()
    return result


@router.get("/cases/{case_id}/members", response_model=list[dto.CaseMember])
async def members(
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    _, case = access
    rows = (
        await db.execute(
            select(CaseMembership, User)
            .join(User, User.id == CaseMembership.user_id)
            .where(CaseMembership.case_id == case.id)
            .order_by(User.username)
        )
    ).all()
    return [
        dto.CaseMember(
            user=ActorRef(kind="USER", id=user.id, display=user.display_name),
            role=member.role,
            added_at=member.created_at,
        )
        for member, user in rows
    ]


async def change_member(db, actor, case, user_id, role):
    service.ensure_open(case)
    await db.execute(select(Case.id).where(Case.id == case.id).with_for_update())
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise NotFound("Resource not found")
    member = await db.get(CaseMembership, (case.id, user_id))
    if member and member.role == "OWNER" and role != "OWNER":
        owners = await db.scalar(
            select(func.count())
            .select_from(CaseMembership)
            .where(CaseMembership.case_id == case.id, CaseMembership.role == "OWNER")
        )
        if owners <= 1:
            raise Conflict("A case must retain at least one owner")
    if role is None:
        if not member:
            raise NotFound("Resource not found")
        await db.delete(member)
    elif member:
        member.role = role
    else:
        member = CaseMembership(case_id=case.id, user_id=user_id, role=role, added_by=actor.user_id)
        db.add(member)
    await record(
        db,
        actor=actor,
        action="case.member_change",
        case_id=case.id,
        target_type="user",
        target_id=user_id,
        detail={"role": role},
    )
    await db.flush()
    result = (
        dto.CaseMember(
            user=ActorRef(kind="USER", id=user.id, display=user.display_name),
            role=role,
            added_at=member.created_at,
        )
        if role
        else None
    )
    await db.commit()
    return result


@router.post("/cases/{case_id}/members", response_model=dto.CaseMember, status_code=201)
async def add_member(
    body: dto.MemberCreate,
    access=Depends(require_case(P.CASE_MANAGE_MEMBERS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await change_member(db, *access, body.user_id, body.role)


@router.patch("/cases/{case_id}/members/{user_id}", response_model=dto.CaseMember)
async def patch_member(
    user_id: UUID,
    body: dto.MemberPatch,
    access=Depends(require_case(P.CASE_MANAGE_MEMBERS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await change_member(db, *access, user_id, body.role)


@router.delete("/cases/{case_id}/members/{user_id}", status_code=204)
async def remove_member(
    user_id: UUID,
    access=Depends(require_case(P.CASE_MANAGE_MEMBERS)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await change_member(db, *access, user_id, None)


@router.get("/cases/{case_id}/timeline", response_model=Page[dto.TimelineEntry])
async def timeline(
    kind: str | None = None,
    from_at: datetime | None = Query(None, alias="from"),
    to_at: datetime | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    _, case = access
    if any(value is not None and value.tzinfo is None for value in (from_at, to_at)):
        raise Validation("Timeline dates require timezones")
    if from_at and to_at and from_at > to_at:
        raise Validation("Timeline window starts after it ends")
    statement = select(AuditEvent).where(AuditEvent.case_id == case.id)
    if kind:
        statement = statement.where(AuditEvent.action.startswith(kind))
    if from_at:
        statement = statement.where(AuditEvent.at >= from_at)
    if to_at:
        statement = statement.where(AuditEvent.at <= to_at)
    rows, next_cursor, total = await page_rows(
        db, statement, AuditEvent, limit=limit, cursor=cursor, newest_by=AuditEvent.at
    )
    items = [
        dto.TimelineEntry(
            at=row.at,
            kind=row.action,
            title=row.action.replace(".", " "),
            ref=ResourceRef(type=row.target_type or "audit", id=row.target_id or row.id),
            actor=ActorRef(kind=row.actor_kind, id=row.actor_id, display=row.actor_kind),
        )
        for row in rows
    ]
    return Page(items=items, next_cursor=next_cursor, total=total)


@router.get("/cases/{case_id}/summary", response_model=dto.CaseSummary)
async def summary(
    access=Depends(require_case(P.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    from darknetra.agent.models import Thread
    from darknetra.analytics.models import LinkCandidate
    from darknetra.evidence.models import Evidence
    from darknetra.extract.models import Observation
    from darknetra.monitor.models import Alert, WatchlistItem

    _, case = access

    async def counts(model, column):
        return dict(
            (
                await db.execute(
                    select(column, func.count()).where(model.case_id == case.id).group_by(column)
                )
            ).all()
        )

    async def count(model, *filters):
        return (
            await db.scalar(
                select(func.count()).select_from(model).where(model.case_id == case.id, *filters)
            )
            or 0
        )

    return dto.CaseSummary(
        evidence_by_class=await counts(Evidence, Evidence.source_class),
        evidence_by_status=await counts(Evidence, Evidence.status),
        observations_by_type=await counts(Observation, Observation.type),
        pending_candidates=await count(LinkCandidate, LinkCandidate.status == "PENDING"),
        open_alerts=await count(Alert, Alert.status == "OPEN"),
        active_items=await count(WatchlistItem, WatchlistItem.active.is_(True)),
        threads=await count(Thread),
        last_activity_at=await db.scalar(
            select(func.max(AuditEvent.at)).where(AuditEvent.case_id == case.id)
        ),
    )
