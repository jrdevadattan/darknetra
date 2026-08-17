from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
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
from sqlalchemy import select

ORIGIN = "http://localhost:3000"


@pytest.fixture(autouse=True)
async def clean_case_state() -> None:
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


def make_user(username: str, role: GlobalRole) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=username,
        password_hash="not-used",
        global_roles=[role],
        is_active=True,
        must_change_password=False,
    )


async def issue_session(session, user: User) -> tuple[str, str]:
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
    access = create_access_token(
        user_id=user.id,
        session_id=auth_session.id,
        signing_key_b64=get_settings().require_jwt_signing_key_b64(),
    )
    return access, csrf


async def add_membership(session, case: Case, user: User, role: GlobalRole) -> None:
    membership = CaseMembership(case_id=case.id, user_id=user.id)
    session.add(membership)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=membership.id, role=role))


async def seed_owner_with_hidden_case() -> tuple[User, Case, str, str]:
    async with async_session_factory() as session:
        owner = make_user("case-owner", GlobalRole.CASE_OWNER)
        hidden_owner = make_user("hidden-owner", GlobalRole.CASE_OWNER)
        session.add_all([owner, hidden_owner])
        await session.flush()
        hidden = Case(
            case_code="HIDDEN-001",
            title="Hidden investigation",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=hidden_owner.id,
            source_authority_summary="Synthetic hidden authority",
        )
        session.add(hidden)
        await session.flush()
        await add_membership(session, hidden, hidden_owner, GlobalRole.CASE_OWNER)
        access, csrf = await issue_session(session, owner)
        await session.commit()
        return owner, hidden, access, csrf


def authenticated_client(access: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://api.test")
    client.cookies.set("darknetra_access", access, domain="api.test", path="/")
    return client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_create_list_retrieve_update_close_reopen_and_audit() -> None:
    owner, hidden, access, csrf = await seed_owner_with_hidden_case()
    async with authenticated_client(access) as client:
        missing_csrf = await client.post(
            "/api/v1/cases",
            headers={"Origin": ORIGIN},
            json={
                "case_code": "CHD-2026-001",
                "title": "Synthetic narcotics case",
                "sensitivity": "STANDARD",
                "source_authority_summary": "Authorized synthetic fixture",
            },
        )
        assert missing_csrf.status_code == 403

        created = await client.post(
            "/api/v1/cases",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            json={
                "case_code": "CHD-2026-001",
                "title": "  Synthetic narcotics case  ",
                "sensitivity": "STANDARD",
                "source_authority_summary": "  Authorized synthetic fixture  ",
            },
        )
        assert created.status_code == 201
        body = created.json()
        case_id = body["id"]
        assert body["case_code"] == "CHD-2026-001"
        assert body["title"] == "Synthetic narcotics case"
        assert body["source_authority_summary"] == "Authorized synthetic fixture"
        assert body["owner_user_id"] == str(owner.id)
        assert body["status"] == "OPEN"
        assert body["closed_at"] is None

        invalid_code = await client.post(
            "/api/v1/cases",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            json={
                "case_code": "lower-case",
                "title": "Valid title",
                "sensitivity": "STANDARD",
                "source_authority_summary": "Authorized synthetic fixture",
            },
        )
        assert invalid_code.status_code == 422

        listed = await client.get("/api/v1/cases?limit=25&offset=0")
        assert listed.status_code == 200
        listing = listed.json()
        assert listing["limit"] == 25
        assert listing["offset"] == 0
        visible_ids = {item["id"] for item in listing["items"]}
        assert case_id in visible_ids
        assert str(hidden.id) not in visible_ids

        retrieved = await client.get(f"/api/v1/cases/{case_id}")
        assert retrieved.status_code == 200
        assert retrieved.json()["case_code"] == "CHD-2026-001"

        updated = await client.patch(
            f"/api/v1/cases/{case_id}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            json={
                "title": "  Updated case title  ",
                "sensitivity": "RESTRICTED",
                "source_authority_summary": "Updated synthetic authority",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Updated case title"
        assert updated.json()["sensitivity"] == "RESTRICTED"

        closed = await client.post(
            f"/api/v1/cases/{case_id}/close",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "CLOSED"
        assert closed.json()["closed_at"] is not None

        double_close = await client.post(
            f"/api/v1/cases/{case_id}/close",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        assert double_close.status_code == 409

        reopened = await client.post(
            f"/api/v1/cases/{case_id}/reopen",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "OPEN"
        assert reopened.json()["closed_at"] is None

    async with async_session_factory() as session:
        membership = await session.scalar(
            select(CaseMembership).where(
                CaseMembership.case_id == case_id,
                CaseMembership.user_id == owner.id,
            )
        )
        assert membership is not None
        roles = set(
            (
                await session.scalars(
                    select(CaseMembershipRole.role).where(
                        CaseMembershipRole.membership_id == membership.id
                    )
                )
            ).all()
        )
        assert roles == {GlobalRole.CASE_OWNER}
        event_types = set((await session.scalars(select(AuditEvent.event_type))).all())
        assert {"CASE_CREATED", "CASE_UPDATED", "CASE_CLOSED", "CASE_REOPENED"} <= event_types


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_routes_mask_inaccessible_cases_as_not_found() -> None:
    _, hidden, _, _ = await seed_owner_with_hidden_case()
    async with async_session_factory() as session:
        analyst = make_user("unassigned-analyst", GlobalRole.ANALYST)
        session.add(analyst)
        await session.flush()
        access, _ = await issue_session(session, analyst)
        await session.commit()

    async with authenticated_client(access) as client:
        inaccessible = await client.get(f"/api/v1/cases/{hidden.id}")
        unknown = await client.get(f"/api/v1/cases/{uuid4()}")

    assert inaccessible.status_code == unknown.status_code == 404
    assert inaccessible.json() == unknown.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_failure_rolls_back_case_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, access, csrf = await seed_owner_with_hidden_case()
    async with authenticated_client(access) as client:
        created = await client.post(
            "/api/v1/cases",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            json={
                "case_code": "ROLLBACK-001",
                "title": "Rollback source title",
                "sensitivity": "STANDARD",
                "source_authority_summary": "Authorized synthetic fixture",
            },
        )
        assert created.status_code == 201
        case_id = created.json()["id"]

        def fail_audit(*args, **kwargs) -> None:
            del args, kwargs
            raise RuntimeError("synthetic audit failure")

        monkeypatch.setattr("darknetra_api.services.cases.append_audit_event", fail_audit)
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            await client.patch(
                f"/api/v1/cases/{case_id}",
                headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                json={"title": "This mutation must roll back"},
            )

    async with async_session_factory() as session:
        stored = await session.get(Case, case_id)
        assert stored is not None
        assert stored.title == "Rollback source title"
