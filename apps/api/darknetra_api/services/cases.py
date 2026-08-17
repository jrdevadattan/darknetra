from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import CaseNotFound, authorize_case, authorize_global
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseStatus, GlobalRole
from darknetra_api.models.user import User, utc_now
from darknetra_api.repositories.cases import get_case_by_code, get_case_by_id
from darknetra_api.schemas.cases import CaseCreateRequest, CaseUpdateRequest
from darknetra_api.services.audit import append_audit_event


class CaseLifecycleConflict(RuntimeError):
    pass


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise CaseLifecycleConflict(message) from exc


async def create_case(
    session: AsyncSession,
    *,
    actor: User,
    payload: CaseCreateRequest,
    request_id: str,
) -> Case:
    authorize_global(actor, Permission.CASE_CREATE)
    if await get_case_by_code(session, payload.case_code) is not None:
        raise CaseLifecycleConflict("case code already exists")

    case = Case(
        case_code=payload.case_code,
        title=payload.title,
        status=CaseStatus.OPEN,
        sensitivity=payload.sensitivity,
        owner_user_id=actor.id,
        source_authority_summary=payload.source_authority_summary,
    )
    session.add(case)
    await session.flush()

    membership = CaseMembership(case_id=case.id, user_id=actor.id)
    session.add(membership)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=membership.id, role=GlobalRole.CASE_OWNER))

    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_CREATED",
        resource_type="case",
        resource_id=str(case.id),
        case_id=case.id,
        request_id=request_id,
        metadata={"case_code": case.case_code},
    )
    await _commit_or_conflict(session, "case code already exists")
    return case


async def update_case(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
    payload: CaseUpdateRequest,
    request_id: str,
) -> Case:
    await authorize_case(actor, case_id, Permission.CASE_UPDATE, session)
    case = await get_case_by_id(session, case_id)
    if case is None:
        raise CaseNotFound("resource not found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(case, field, value)
    case.updated_at = utc_now()
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_UPDATED",
        resource_type="case",
        resource_id=str(case.id),
        case_id=case.id,
        request_id=request_id,
        metadata={"changed_fields": sorted(changes)},
    )
    await session.commit()
    return case


async def close_case(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
    request_id: str,
) -> Case:
    await authorize_case(actor, case_id, Permission.CASE_CLOSE, session)
    case = await get_case_by_id(session, case_id)
    if case is None:
        raise CaseNotFound("resource not found")
    if case.status is CaseStatus.CLOSED:
        raise CaseLifecycleConflict("case is already closed")

    now = utc_now()
    case.status = CaseStatus.CLOSED
    case.closed_at = now
    case.updated_at = now
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_CLOSED",
        resource_type="case",
        resource_id=str(case.id),
        case_id=case.id,
        request_id=request_id,
    )
    await session.commit()
    return case


async def reopen_case(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
    request_id: str,
) -> Case:
    await authorize_case(actor, case_id, Permission.CASE_REOPEN, session)
    case = await get_case_by_id(session, case_id)
    if case is None:
        raise CaseNotFound("resource not found")
    if case.status is not CaseStatus.CLOSED:
        raise CaseLifecycleConflict("only a closed case can be reopened")

    case.status = CaseStatus.OPEN
    case.closed_at = None
    case.updated_at = utc_now()
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_REOPENED",
        resource_type="case",
        resource_id=str(case.id),
        case_id=case.id,
        request_id=request_id,
    )
    await session.commit()
    return case
