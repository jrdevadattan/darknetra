from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User


@dataclass(frozen=True)
class MembershipRecord:
    membership: CaseMembership
    user: User
    roles: tuple[GlobalRole, ...]


async def get_membership(
    session: AsyncSession,
    *,
    case_id: UUID,
    user_id: UUID,
) -> CaseMembership | None:
    return await session.scalar(
        select(CaseMembership).where(
            CaseMembership.case_id == case_id,
            CaseMembership.user_id == user_id,
        )
    )


async def get_membership_roles(
    session: AsyncSession,
    membership_id: UUID,
) -> tuple[GlobalRole, ...]:
    roles = (
        await session.scalars(
            select(CaseMembershipRole.role)
            .where(CaseMembershipRole.membership_id == membership_id)
            .order_by(CaseMembershipRole.role)
        )
    ).all()
    return tuple(roles)


async def get_membership_record(
    session: AsyncSession,
    *,
    case_id: UUID,
    user_id: UUID,
) -> MembershipRecord | None:
    row = (
        await session.execute(
            select(CaseMembership, User)
            .join(User, User.id == CaseMembership.user_id)
            .where(
                CaseMembership.case_id == case_id,
                CaseMembership.user_id == user_id,
            )
        )
    ).one_or_none()
    if row is None:
        return None
    membership, user = row
    return MembershipRecord(
        membership=membership,
        user=user,
        roles=await get_membership_roles(session, membership.id),
    )


async def list_membership_records(
    session: AsyncSession,
    *,
    case_id: UUID,
) -> list[MembershipRecord]:
    rows = (
        await session.execute(
            select(CaseMembership, User)
            .join(User, User.id == CaseMembership.user_id)
            .where(CaseMembership.case_id == case_id)
            .order_by(User.username_normalized, User.id)
        )
    ).all()
    return [
        MembershipRecord(
            membership=membership,
            user=user,
            roles=await get_membership_roles(session, membership.id),
        )
        for membership, user in rows
    ]


async def count_case_owners(session: AsyncSession, *, case_id: UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(CaseMembershipRole)
        .join(
            CaseMembership,
            CaseMembership.id == CaseMembershipRole.membership_id,
        )
        .where(
            CaseMembership.case_id == case_id,
            CaseMembershipRole.role == GlobalRole.CASE_OWNER,
        )
    )
    return int(count or 0)
