from datetime import UTC, datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa
from darknetra_api.authz.policy import ROLE_PERMISSIONS
from darknetra_api.config import get_settings
from darknetra_api.db.session import async_session_factory
from darknetra_api.main import app
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseSensitivity, CaseStatus, GlobalRole
from darknetra_api.models.user import User, utc_now
from darknetra_api.security.csrf import generate_csrf_token, hash_csrf_token
from darknetra_api.security.tokens import (
    REFRESH_TOKEN_LIFETIME,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)


@pytest.fixture(autouse=True)
async def clean_admin_read_state() -> None:
    async with async_session_factory() as session:
        for model in (
            AuditEvent,
            CaseMembershipRole,
            CaseMembership,
            Case,
            AuthSession,
            User,
        ):
            await session.execute(sa.delete(model))
        await session.commit()
    yield
    async with async_session_factory() as session:
        for model in (
            AuditEvent,
            CaseMembershipRole,
            CaseMembership,
            Case,
            AuthSession,
            User,
        ):
            await session.execute(sa.delete(model))
        await session.commit()


def make_user(username: str, role: GlobalRole, *, active: bool = True) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=f"Display {username}",
        password_hash=f"sensitive-password-hash-{username}",
        global_roles=[role],
        is_active=active,
        must_change_password=False,
        failed_login_count=4,
    )


async def issue_access(session, user: User) -> str:
    refresh = generate_refresh_token()
    csrf = generate_csrf_token()
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh),
        csrf_token_hash=hash_csrf_token(csrf),
        expires_at=utc_now() + REFRESH_TOKEN_LIFETIME,
    )
    session.add(auth_session)
    await session.flush()
    return create_access_token(
        user_id=user.id,
        session_id=auth_session.id,
        signing_key_b64=get_settings().require_jwt_signing_key_b64(),
    )


async def add_membership(session, case: Case, user: User, role: GlobalRole) -> None:
    membership = CaseMembership(case_id=case.id, user_id=user.id)
    session.add(membership)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=membership.id, role=role))


async def seed_admin_reads() -> dict[str, object]:
    async with async_session_factory() as session:
        admin = make_user("admin", GlobalRole.ADMIN)
        owner = make_user("owner", GlobalRole.CASE_OWNER)
        analyst = make_user("analyst", GlobalRole.ANALYST, active=False)
        auditor = make_user("auditor", GlobalRole.AUDITOR)
        hidden_owner = make_user("hidden-owner", GlobalRole.CASE_OWNER)
        session.add_all([admin, owner, analyst, auditor, hidden_owner])
        await session.flush()

        visible_case = Case(
            case_code="ADMIN-READ-001",
            title="Visible audit case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic audit authority",
        )
        hidden_case = Case(
            case_code="ADMIN-READ-002",
            title="Hidden audit case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=hidden_owner.id,
            source_authority_summary="Synthetic hidden authority",
        )
        session.add_all([visible_case, hidden_case])
        await session.flush()
        await add_membership(session, visible_case, owner, GlobalRole.CASE_OWNER)
        await add_membership(session, hidden_case, hidden_owner, GlobalRole.CASE_OWNER)

        now = datetime.now(UTC)
        session.add_all(
            [
                AuditEvent(
                    actor_user_id=owner.id,
                    event_type="VISIBLE_EVENT",
                    resource_type="case",
                    resource_id=str(visible_case.id),
                    case_id=visible_case.id,
                    request_id="req-visible",
                    metadata_json={"scope": "visible"},
                    created_at=now - timedelta(minutes=3),
                ),
                AuditEvent(
                    actor_user_id=hidden_owner.id,
                    event_type="HIDDEN_EVENT",
                    resource_type="case",
                    resource_id=str(hidden_case.id),
                    case_id=hidden_case.id,
                    request_id="req-hidden",
                    metadata_json={"scope": "hidden"},
                    created_at=now - timedelta(minutes=2),
                ),
                AuditEvent(
                    actor_user_id=None,
                    event_type="SYSTEM_EVENT",
                    resource_type="system",
                    resource_id="system",
                    case_id=None,
                    request_id="req-system",
                    metadata_json={"scope": "system"},
                    created_at=now - timedelta(minutes=1),
                ),
            ]
        )

        admin_access = await issue_access(session, admin)
        owner_access = await issue_access(session, owner)
        auditor_access = await issue_access(session, auditor)
        analyst.is_active = True
        analyst_access = await issue_access(session, analyst)
        analyst.is_active = False
        await session.commit()
        return {
            "admin": admin,
            "owner": owner,
            "analyst": analyst,
            "auditor": auditor,
            "visible_case": visible_case,
            "hidden_case": hidden_case,
            "admin_access": admin_access,
            "owner_access": owner_access,
            "auditor_access": auditor_access,
            "analyst_access": analyst_access,
            "now": now,
        }


def authenticated_client(access: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://api.test")
    client.cookies.set("darknetra_access", access, domain="api.test", path="/")
    return client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_list_is_authorized_and_strictly_redacted() -> None:
    fixture = await seed_admin_reads()
    for access_key in ("admin_access", "owner_access"):
        async with authenticated_client(str(fixture[access_key])) as client:
            response = await client.get("/api/v1/users")
        assert response.status_code == 200
        assert response.json()["items"]
        for row in response.json()["items"]:
            assert set(row) == {"id", "username", "display_name", "is_active", "global_roles"}
        serialized = response.text.lower()
        assert "password_hash" not in serialized
        assert "refresh_token" not in serialized
        assert "csrf_token" not in serialized
        assert "failed_login" not in serialized
        assert "locked_until" not in serialized
        assert "sensitive-password-hash" not in serialized

    async with authenticated_client(str(fixture["analyst_access"])) as client:
        denied = await client.get("/api/v1/users")
    assert denied.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_role_matrix_is_rendered_from_enforcement_policy_source() -> None:
    fixture = await seed_admin_reads()
    async with authenticated_client(str(fixture["owner_access"])) as client:
        response = await client.get("/api/v1/admin/roles")
    assert response.status_code == 200
    matrix = {row["role"]: set(row["permissions"]) for row in response.json()["roles"]}
    expected = {
        role.value: {permission.value for permission in permissions}
        for role, permissions in ROLE_PERMISSIONS.items()
    }
    assert matrix == expected


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_reads_are_paginated_filterable_and_case_scoped() -> None:
    fixture = await seed_admin_reads()
    visible_case = fixture["visible_case"]
    assert isinstance(visible_case, Case)

    async with authenticated_client(str(fixture["owner_access"])) as client:
        owner_view = await client.get("/api/v1/audit?limit=25&offset=0")
    assert owner_view.status_code == 200
    owner_events = [row["event_type"] for row in owner_view.json()["items"]]
    assert owner_events == ["VISIBLE_EVENT"]
    assert owner_view.json()["items"][0]["metadata_json"] == {"scope": "visible"}

    async with authenticated_client(str(fixture["auditor_access"])) as client:
        first_page = await client.get("/api/v1/audit?limit=2&offset=0")
        second_page = await client.get("/api/v1/audit?limit=2&offset=2")
    assert first_page.status_code == second_page.status_code == 200
    assert [row["event_type"] for row in first_page.json()["items"]] == [
        "SYSTEM_EVENT",
        "HIDDEN_EVENT",
    ]
    assert [row["event_type"] for row in second_page.json()["items"]] == ["VISIBLE_EVENT"]
    assert first_page.json()["has_more"] is True
    assert second_page.json()["has_more"] is False

    async with authenticated_client(str(fixture["admin_access"])) as client:
        filtered = await client.get(
            "/api/v1/audit",
            params={
                "case_id": str(visible_case.id),
                "event_type": "VISIBLE_EVENT",
                "resource_type": "case",
                "from_time": (fixture["now"] - timedelta(minutes=4)).isoformat(),
                "to_time": fixture["now"].isoformat(),
            },
        )
    assert filtered.status_code == 200
    assert [row["event_type"] for row in filtered.json()["items"]] == ["VISIBLE_EVENT"]
