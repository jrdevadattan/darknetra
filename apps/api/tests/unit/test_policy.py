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
            Permission.EVIDENCE_CREATE,
            Permission.CASE_MEMBERSHIP_MANAGE,
            Permission.USER_READ,
            Permission.ROLE_READ,
            Permission.AUDIT_READ,
        }
    ),
    GlobalRole.COLLECTOR: frozenset({Permission.CASE_READ, Permission.EVIDENCE_CREATE}),
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
    with pytest.raises(AuthorizationDenied):
        authorize_global(analyst, Permission.CASE_CREATE)


def test_only_case_owners_and_collectors_receive_evidence_create_permission() -> None:
    assert Permission.EVIDENCE_CREATE in ROLE_PERMISSIONS[GlobalRole.CASE_OWNER]
    assert Permission.EVIDENCE_CREATE in ROLE_PERMISSIONS[GlobalRole.COLLECTOR]
    for role in (
        GlobalRole.ANALYST,
        GlobalRole.REVIEWER,
        GlobalRole.AUDITOR,
        GlobalRole.VIEWER,
    ):
        assert Permission.EVIDENCE_CREATE not in ROLE_PERMISSIONS[role]


def test_forced_password_change_blocks_normal_mutations_not_safe_reads() -> None:
    admin = make_user(GlobalRole.ADMIN, must_change_password=True)

    authorize_global(admin, Permission.ROLE_READ)
    with pytest.raises(PasswordChangeRequired):
        authorize_global(admin, Permission.CASE_CREATE)
    with pytest.raises(PasswordChangeRequired):
        authorize_global(admin, Permission.USER_MANAGE)
