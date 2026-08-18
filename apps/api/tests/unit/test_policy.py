import pytest
from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import (
    ROLE_PERMISSIONS,
    AuthorizationDenied,
    PasswordChangeRequired,
    authorize_global,
)
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User

EXPECTED_ROLE_PERMISSIONS = {
    GlobalRole.ADMIN: frozenset(Permission),
    GlobalRole.CASE_OWNER: frozenset(
        {
            Permission.CASE_CREATE,
            Permission.CASE_READ,
            Permission.CASE_UPDATE,
            Permission.CASE_CLOSE,
            Permission.CASE_REOPEN,
            Permission.CASE_MEMBERSHIP_MANAGE,
            Permission.SENSITIVE_VALUE_REVEAL,
            Permission.USER_READ,
            Permission.ROLE_READ,
            Permission.AUDIT_READ,
        }
    ),
    GlobalRole.COLLECTOR: frozenset({Permission.CASE_READ}),
    GlobalRole.ANALYST: frozenset(
        {Permission.CASE_READ, Permission.SENSITIVE_VALUE_REVEAL}
    ),
    GlobalRole.REVIEWER: frozenset(
        {
            Permission.CASE_READ,
            Permission.SENSITIVE_VALUE_REVEAL,
            Permission.AUDIT_READ,
        }
    ),
    GlobalRole.AUDITOR: frozenset(
        {
            Permission.CASE_READ,
            Permission.SENSITIVE_VALUE_REVEAL,
            Permission.ROLE_READ,
            Permission.AUDIT_READ,
            Permission.SYSTEM_HEALTH_READ,
        }
    ),
    GlobalRole.VIEWER: frozenset({Permission.CASE_READ}),
}


def make_user(*roles: GlobalRole, must_change_password: bool = False) -> User:
    return User(
        username="policy-user",
        username_normalized="policy-user",
        display_name="Policy User",
        password_hash="not-used",
        global_roles=list(roles),
        is_active=True,
        must_change_password=must_change_password,
    )


def test_role_permission_map_is_explicit_and_immutable() -> None:
    assert dict(ROLE_PERMISSIONS) == EXPECTED_ROLE_PERMISSIONS
    with pytest.raises(TypeError):
        ROLE_PERMISSIONS[GlobalRole.ADMIN] = frozenset()  # type: ignore[index]


def test_global_authorization_uses_current_role_state() -> None:
    owner = make_user(GlobalRole.CASE_OWNER)
    analyst = make_user(GlobalRole.ANALYST)
    admin = make_user(GlobalRole.ADMIN)

    authorize_global(owner, Permission.CASE_CREATE)
    authorize_global(admin, Permission.USER_MANAGE)
    authorize_global(analyst, Permission.SENSITIVE_VALUE_REVEAL)
    with pytest.raises(AuthorizationDenied):
        authorize_global(analyst, Permission.CASE_CREATE)


def test_forced_password_change_blocks_normal_mutations_and_sensitive_reveals() -> None:
    admin = make_user(GlobalRole.ADMIN, must_change_password=True)

    authorize_global(admin, Permission.ROLE_READ)
    with pytest.raises(PasswordChangeRequired):
        authorize_global(admin, Permission.CASE_CREATE)
    with pytest.raises(PasswordChangeRequired):
        authorize_global(admin, Permission.USER_MANAGE)
    with pytest.raises(PasswordChangeRequired):
        authorize_global(admin, Permission.SENSITIVE_VALUE_REVEAL)
