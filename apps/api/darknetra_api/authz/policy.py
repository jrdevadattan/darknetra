from types import MappingProxyType
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User


class AuthorizationDenied(PermissionError):
    """The authenticated user does not hold the required effective permission."""


class CaseNotFound(AuthorizationDenied):
    """Case absence and case invisibility intentionally share one domain outcome."""


class PasswordChangeRequired(AuthorizationDenied):
    """Bootstrap credentials must be replaced before normal mutations are allowed."""


ROLE_PERMISSIONS = MappingProxyType(
    {
        GlobalRole.ADMIN: frozenset(Permission),
        GlobalRole.CASE_OWNER: frozenset(
            {
                Permission.CASE_CREATE,
                Permission.CASE_READ,
                Permission.CASE_UPDATE,
                Permission.CASE_CLOSE,
                Permission.CASE_REOPEN,
                Permission.CASE_MEMBERSHIP_MANAGE,
                Permission.USER_READ,
                Permission.ROLE_READ,
                Permission.AUDIT_READ,
            }
        ),
        GlobalRole.COLLECTOR: frozenset({Permission.CASE_READ}),
        GlobalRole.ANALYST: frozenset({Permission.CASE_READ}),
        GlobalRole.REVIEWER: frozenset({Permission.CASE_READ, Permission.AUDIT_READ}),
        GlobalRole.AUDITOR: frozenset(
            {
                Permission.CASE_READ,
                Permission.ROLE_READ,
                Permission.AUDIT_READ,
                Permission.SYSTEM_HEALTH_READ,
            }
        ),
        GlobalRole.VIEWER: frozenset({Permission.CASE_READ}),
    }
)

_MUTATION_PERMISSIONS = frozenset(
    {
        Permission.CASE_CREATE,
        Permission.CASE_UPDATE,
        Permission.CASE_CLOSE,
        Permission.CASE_REOPEN,
        Permission.CASE_MEMBERSHIP_MANAGE,
        Permission.USER_MANAGE,
    }
)


def _enforce_password_change(user: User, permission: Permission) -> None:
    if user.must_change_password and permission in _MUTATION_PERMISSIONS:
        raise PasswordChangeRequired("password change required before this operation")


def _has_permission(roles: set[GlobalRole], permission: Permission) -> bool:
    return any(permission in ROLE_PERMISSIONS.get(role, frozenset()) for role in roles)


def authorize_global(user: User, permission: Permission) -> None:
    _enforce_password_change(user, permission)
    if not user.is_active or not _has_permission(set(user.global_roles), permission):
        raise AuthorizationDenied("permission denied")


async def authorize_case(
    user: User,
    case_id: UUID,
    permission: Permission,
    session: AsyncSession,
) -> None:
    _enforce_password_change(user, permission)
    if not user.is_active:
        raise AuthorizationDenied("permission denied")

    case_exists = await session.scalar(select(Case.id).where(Case.id == case_id))
    if case_exists is None:
        raise CaseNotFound("resource not found")

    # ADMIN can repair membership state without first being a case member. This is
    # deliberately limited to the administrative repair permission; the mutation
    # service that uses this path is responsible for appending its audit event.
    if GlobalRole.ADMIN in user.global_roles and permission is Permission.CASE_MEMBERSHIP_MANAGE:
        return

    membership_id = await session.scalar(
        select(CaseMembership.id).where(
            CaseMembership.case_id == case_id,
            CaseMembership.user_id == user.id,
        )
    )
    if membership_id is None:
        raise CaseNotFound("resource not found")

    membership_roles = set(
        (
            await session.scalars(
                select(CaseMembershipRole.role).where(
                    CaseMembershipRole.membership_id == membership_id
                )
            )
        ).all()
    )
    effective_roles = membership_roles.intersection(set(user.global_roles))
    if not _has_permission(effective_roles, permission):
        raise AuthorizationDenied("permission denied")
