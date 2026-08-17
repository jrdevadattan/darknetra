from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import ROLE_PERMISSIONS
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User


async def get_case_by_id(session: AsyncSession, case_id: UUID) -> Case | None:
    return await session.get(Case, case_id)


async def get_case_by_code(session: AsyncSession, case_code: str) -> Case | None:
    return await session.scalar(select(Case).where(Case.case_code == case_code))


async def list_visible_cases(
    session: AsyncSession,
    *,
    user: User,
    limit: int,
    offset: int,
) -> tuple[list[Case], bool]:
    readable_roles = [
        role
        for role in user.global_roles
        if role is not GlobalRole.ADMIN and Permission.CASE_READ in ROLE_PERMISSIONS.get(role, frozenset())
    ]
    if not readable_roles:
        return [], False

    statement = (
        select(Case)
        .join(CaseMembership, CaseMembership.case_id == Case.id)
        .join(
            CaseMembershipRole,
            CaseMembershipRole.membership_id == CaseMembership.id,
        )
        .where(
            CaseMembership.user_id == user.id,
            CaseMembershipRole.role.in_(readable_roles),
        )
        .distinct()
        .order_by(Case.updated_at.desc(), Case.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list((await session.scalars(statement)).all())
    return rows[:limit], len(rows) > limit
