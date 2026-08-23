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
async def clean_membership_state() -> None:
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


def make_user(username: str, *roles: GlobalRole) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=username,
        password_hash="not-used",
        global_roles=list(roles),
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


async def add_membership(session, case: Case, user: User, *roles: GlobalRole) -> CaseMembership:
    membership = CaseMembership(case_id=case.id, user_id=user.id)
    session.add(membership)
    await session.flush()
    for role in roles:
        session.add(CaseMembershipRole(membership_id=membership.id, role=role))
    return membership


async def seed_membership_fixture() -> dict[str, object]:
    async with async_session_factory() as session:
        owner = make_user("owner", GlobalRole.CASE_OWNER, GlobalRole.REVIEWER)
        member = make_user("member", GlobalRole.ANALYST, GlobalRole.REVIEWER)
        candidate = make_user("candidate", GlobalRole.REVIEWER)
        second_owner = make_user("second-owner", GlobalRole.CASE_OWNER)
        hidden_owner = make_user("hidden-owner", GlobalRole.CASE_OWNER)
        admin = make_user("admin", GlobalRole.ADMIN)
        outsider = make_user("outsider", GlobalRole.ANALYST)
        session.add_all(
            [owner, member, candidate, second_owner, hidden_owner, admin, outsider]
        )
        await session.flush()

        case = Case(
            case_code="MEMBERS-001",
            title="Membership test case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic membership fixture",
        )
        hidden = Case(
            case_code="MEMBERS-002",
            title="Hidden membership case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=hidden_owner.id,
            source_authority_summary="Synthetic hidden membership fixture",
        )
        session.add_all([case, hidden])
        await session.flush()
        await add_membership(session, case, owner, GlobalRole.CASE_OWNER)
        await add_membership(session, hidden, hidden_owner, GlobalRole.CASE_OWNER)

        owner_access, owner_csrf = await issue_session(session, owner)
        admin_access, admin_csrf = await issue_session(session, admin)
        outsider_access, _ = await issue_session(session, outsider)
        await session.commit()
        return {
            "owner": owner,
            "member": member,
            "candidate": candidate,
            "second_owner": second_owner,
            "admin": admin,
            "case": case,
            "hidden": hidden,
            "owner_access": owner_access,
            "owner_csrf": owner_csrf,
            "admin_access": admin_access,
            "admin_csrf": admin_csrf,
            "outsider_access": outsider_access,
        }


def authenticated_client(access: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://api.test")
    client.cookies.set("darknetra_access", access, domain="api.test", path="/")
    return client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_owner_can_add_list_update_and_remove_members_with_audit() -> None:
    fixture = await seed_membership_fixture()
    case = fixture["case"]
    member = fixture["member"]
    candidate = fixture["candidate"]
    owner = fixture["owner"]
    assert isinstance(case, Case)
    assert isinstance(member, User)
    assert isinstance(candidate, User)
    assert isinstance(owner, User)

    async with authenticated_client(str(fixture["owner_access"])) as client:
        no_csrf = await client.post(
            f"/api/v1/cases/{case.id}/members",
            headers={"Origin": ORIGIN},
            json={"user_id": str(member.id), "roles": ["ANALYST"]},
        )
        assert no_csrf.status_code == 403

        added = await client.post(
            f"/api/v1/cases/{case.id}/members",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
            json={"user_id": str(member.id), "roles": ["ANALYST"]},
        )
        assert added.status_code == 201
        assert added.json()["user_id"] == str(member.id)
        assert added.json()["roles"] == ["ANALYST"]

        duplicate = await client.post(
            f"/api/v1/cases/{case.id}/members",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
            json={"user_id": str(member.id), "roles": ["ANALYST"]},
        )
        assert duplicate.status_code == 409

        admin_role = await client.post(
            f"/api/v1/cases/{case.id}/members",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
            json={"user_id": str(candidate.id), "roles": ["ADMIN"]},
        )
        assert admin_role.status_code == 422

        listed = await client.get(f"/api/v1/cases/{case.id}/members")
        assert listed.status_code == 200
        listed_by_user = {row["user_id"]: row for row in listed.json()["items"]}
        assert listed_by_user[str(owner.id)]["roles"] == ["CASE_OWNER"]
        assert listed_by_user[str(member.id)]["roles"] == ["ANALYST"]

        updated = await client.patch(
            f"/api/v1/cases/{case.id}/members/{member.id}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
            json={"roles": ["REVIEWER"]},
        )
        assert updated.status_code == 200
        assert updated.json()["roles"] == ["REVIEWER"]

        owner_role_removal = await client.patch(
            f"/api/v1/cases/{case.id}/members/{owner.id}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
            json={"roles": ["REVIEWER"]},
        )
        assert owner_role_removal.status_code == 409

        owner_delete = await client.delete(
            f"/api/v1/cases/{case.id}/members/{owner.id}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
        )
        assert owner_delete.status_code == 409

        removed = await client.delete(
            f"/api/v1/cases/{case.id}/members/{member.id}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["owner_csrf"])},
        )
        assert removed.status_code == 204

    async with async_session_factory() as session:
        event_rows = (
            await session.execute(
                select(AuditEvent.event_type, AuditEvent.metadata_json).where(
                    AuditEvent.event_type.in_(
                        [
                            "CASE_MEMBERSHIP_ADDED",
                            "CASE_MEMBERSHIP_UPDATED",
                            "CASE_MEMBERSHIP_REMOVED",
                        ]
                    )
                )
            )
        ).all()
        assert {event_type for event_type, _ in event_rows} == {
            "CASE_MEMBERSHIP_ADDED",
            "CASE_MEMBERSHIP_UPDATED",
            "CASE_MEMBERSHIP_REMOVED",
        }
        for _, metadata in event_rows:
            assert set(metadata) == {"affected_user_id", "roles"}
            assert isinstance(metadata["affected_user_id"], str)
            assert isinstance(metadata["roles"], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_can_repair_membership_and_last_case_owner_cannot_be_removed() -> None:
    fixture = await seed_membership_fixture()
    hidden = fixture["hidden"]
    second_owner = fixture["second_owner"]
    assert isinstance(hidden, Case)
    assert isinstance(second_owner, User)

    async with authenticated_client(str(fixture["admin_access"])) as client:
        repaired = await client.post(
            f"/api/v1/cases/{hidden.id}/members",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["admin_csrf"])},
            json={"user_id": str(second_owner.id), "roles": ["CASE_OWNER"]},
        )
        assert repaired.status_code == 201

    async with async_session_factory() as session:
        hidden_owner_membership = await session.scalar(
            select(CaseMembership).where(
                CaseMembership.case_id == hidden.id,
                CaseMembership.user_id == hidden.owner_user_id,
            )
        )
        assert hidden_owner_membership is not None
        await session.execute(
            sa.delete(CaseMembershipRole).where(
                CaseMembershipRole.membership_id == hidden_owner_membership.id
            )
        )
        await session.delete(hidden_owner_membership)
        await session.commit()

    async with authenticated_client(str(fixture["admin_access"])) as client:
        last_owner_delete = await client.delete(
            f"/api/v1/cases/{hidden.id}/members/{second_owner.id}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": str(fixture["admin_csrf"])},
        )
        assert last_owner_delete.status_code == 409

    async with async_session_factory() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "CASE_MEMBERSHIP_ADDED",
                AuditEvent.actor_user_id == fixture["admin"].id,
                AuditEvent.case_id == hidden.id,
            )
        )
        assert event is not None
        assert event.metadata_json == {
            "affected_user_id": str(second_owner.id),
            "roles": ["CASE_OWNER"],
        }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inaccessible_membership_case_matches_unknown_case_404() -> None:
    fixture = await seed_membership_fixture()
    hidden = fixture["hidden"]
    assert isinstance(hidden, Case)

    async with authenticated_client(str(fixture["outsider_access"])) as client:
        inaccessible = await client.get(f"/api/v1/cases/{hidden.id}/members")
        unknown = await client.get(f"/api/v1/cases/{uuid4()}/members")

    assert inaccessible.status_code == unknown.status_code == 404
    assert inaccessible.json() == unknown.json()
