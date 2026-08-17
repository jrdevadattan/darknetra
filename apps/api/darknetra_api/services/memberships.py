from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import CaseNotFound, authorize_case
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.repositories.memberships import (
    MembershipRecord,
    count_case_owners,
    get_membership,
    get_membership_record,
    get_membership_roles,
    list_membership_records,
)
from darknetra_api.services.audit import append_audit_event


class MembershipConflict(RuntimeError):
    pass


class MembershipNotFound(RuntimeError):
    pass


def _sorted_roles(roles: set[GlobalRole] | tuple[GlobalRole, ...]) -> list[str]:
    return sorted(role.value for role in roles)


def _validate_target_roles(target: User, roles: set[GlobalRole]) -> None:
    if GlobalRole.ADMIN in roles:
        raise MembershipConflict("ADMIN cannot be assigned as a case role")
    if not roles.issubset(set(target.global_roles)):
        raise MembershipConflict("case roles must be a subset of the user's global roles")


async def list_case_members(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
) -> list[MembershipRecord]:
    await authorize_case(actor, case_id, Permission.CASE_MEMBERSHIP_MANAGE, session)
    return await list_membership_records(session, case_id=case_id)


async def add_case_member(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
    target_user_id: UUID,
    roles: set[GlobalRole],
    request_id: str,
) -> MembershipRecord:
    await authorize_case(actor, case_id, Permission.CASE_MEMBERSHIP_MANAGE, session)
    case = await session.get(Case, case_id)
    if case is None:
        raise CaseNotFound("resource not found")
    target = await session.get(User, target_user_id)
    if target is None or not target.is_active:
        raise MembershipNotFound("user not found")
    _validate_target_roles(target, roles)
    if await get_membership(session, case_id=case_id, user_id=target_user_id) is not None:
        raise MembershipConflict("user is already a case member")

    membership = CaseMembership(case_id=case_id, user_id=target_user_id)
    session.add(membership)
    await session.flush()
    for role in roles:
        session.add(CaseMembershipRole(membership_id=membership.id, role=role))
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_MEMBERSHIP_ADDED",
        resource_type="case_membership",
        resource_id=str(membership.id),
        case_id=case_id,
        request_id=request_id,
        metadata={
            "affected_user_id": str(target_user_id),
            "roles": _sorted_roles(roles),
        },
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise MembershipConflict("user is already a case member") from exc
    record = await get_membership_record(session, case_id=case_id, user_id=target_user_id)
    if record is None:
        raise MembershipNotFound("membership not found")
    return record


async def update_case_member(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
    target_user_id: UUID,
    roles: set[GlobalRole],
    request_id: str,
) -> MembershipRecord:
    await authorize_case(actor, case_id, Permission.CASE_MEMBERSHIP_MANAGE, session)
    case = await session.get(Case, case_id)
    if case is None:
        raise CaseNotFound("resource not found")
    target = await session.get(User, target_user_id)
    if target is None:
        raise MembershipNotFound("user not found")
    _validate_target_roles(target, roles)
    membership = await get_membership(session, case_id=case_id, user_id=target_user_id)
    if membership is None:
        raise MembershipNotFound("membership not found")
    if target_user_id == case.owner_user_id and GlobalRole.CASE_OWNER not in roles:
        raise MembershipConflict("case owner must retain CASE_OWNER membership")

    existing_roles = set(await get_membership_roles(session, membership.id))
    if GlobalRole.CASE_OWNER in existing_roles and GlobalRole.CASE_OWNER not in roles:
        if await count_case_owners(session, case_id=case_id) <= 1:
            raise MembershipConflict("cannot remove the last CASE_OWNER")

    await session.execute(
        sa.delete(CaseMembershipRole).where(
            CaseMembershipRole.membership_id == membership.id
        )
    )
    for role in roles:
        session.add(CaseMembershipRole(membership_id=membership.id, role=role))
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_MEMBERSHIP_UPDATED",
        resource_type="case_membership",
        resource_id=str(membership.id),
        case_id=case_id,
        request_id=request_id,
        metadata={
            "affected_user_id": str(target_user_id),
            "roles": _sorted_roles(roles),
        },
    )
    await session.commit()
    record = await get_membership_record(session, case_id=case_id, user_id=target_user_id)
    if record is None:
        raise MembershipNotFound("membership not found")
    return record


async def remove_case_member(
    session: AsyncSession,
    *,
    actor: User,
    case_id: UUID,
    target_user_id: UUID,
    request_id: str,
) -> None:
    await authorize_case(actor, case_id, Permission.CASE_MEMBERSHIP_MANAGE, session)
    case = await session.get(Case, case_id)
    if case is None:
        raise CaseNotFound("resource not found")
    membership = await get_membership(session, case_id=case_id, user_id=target_user_id)
    if membership is None:
        raise MembershipNotFound("membership not found")
    if target_user_id == case.owner_user_id:
        raise MembershipConflict("case owner membership cannot be removed")

    roles = set(await get_membership_roles(session, membership.id))
    if GlobalRole.CASE_OWNER in roles and await count_case_owners(session, case_id=case_id) <= 1:
        raise MembershipConflict("cannot remove the last CASE_OWNER")

    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="CASE_MEMBERSHIP_REMOVED",
        resource_type="case_membership",
        resource_id=str(membership.id),
        case_id=case_id,
        request_id=request_id,
        metadata={
            "affected_user_id": str(target_user_id),
            "roles": _sorted_roles(roles),
        },
    )
    await session.delete(membership)
    await session.commit()
