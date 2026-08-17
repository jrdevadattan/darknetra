from typing import Annotated
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound, authorize_case
from darknetra_api.config import get_settings
from darknetra_api.db.session import async_session_factory
from darknetra_api.dependencies.auth import require_case_permission
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
from fastapi import Depends, FastAPI


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


async def clear_authorization_state() -> None:
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


@pytest.fixture(autouse=True)
async def clean_authorization_state() -> None:
    await clear_authorization_state()
    yield
    await clear_authorization_state()


async def add_membership(session, *, case_id, user_id, role: GlobalRole) -> None:
    membership = CaseMembership(case_id=case_id, user_id=user_id)
    session.add(membership)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=membership.id, role=role))


async def seed_cross_case_fixture() -> tuple[User, Case, Case, str]:
    async with async_session_factory() as session:
        owner = make_user("owner", GlobalRole.CASE_OWNER)
        analyst_a = make_user("analyst-a", GlobalRole.ANALYST)
        analyst_b = make_user("analyst-b", GlobalRole.ANALYST)
        session.add_all([owner, analyst_a, analyst_b])
        await session.flush()

        case_a = Case(
            case_code="AUTHZ-A",
            title="Analyst A case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorization fixture",
        )
        case_b = Case(
            case_code="AUTHZ-B",
            title="Analyst B case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorization fixture",
        )
        session.add_all([case_a, case_b])
        await session.flush()
        await add_membership(session, case_id=case_a.id, user_id=analyst_a.id, role=GlobalRole.ANALYST)
        await add_membership(session, case_id=case_b.id, user_id=analyst_b.id, role=GlobalRole.ANALYST)

        refresh = generate_refresh_token()
        csrf = generate_csrf_token()
        auth_session = AuthSession(
            user_id=analyst_a.id,
            refresh_token_hash=hash_refresh_token(refresh),
            csrf_token_hash=hash_csrf_token(csrf),
            expires_at=utc_now() + REFRESH_TOKEN_LIFETIME,
        )
        session.add(auth_session)
        await session.flush()
        access = create_access_token(
            user_id=analyst_a.id,
            session_id=auth_session.id,
            signing_key_b64=get_settings().require_jwt_signing_key_b64(),
        )
        await session.commit()
        return analyst_a, case_a, case_b, access


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inaccessible_case_and_unknown_case_have_identical_404_shape() -> None:
    _, case_a, case_b, access = await seed_cross_case_fixture()
    test_app = FastAPI()

    @test_app.get("/cases/{case_id}")
    async def probe(
        case: Annotated[Case, Depends(require_case_permission(Permission.CASE_READ))],
    ) -> dict[str, str]:
        return {"id": str(case.id)}

    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        client.cookies.set("darknetra_access", access, domain="api.test", path="/")
        visible = await client.get(f"/cases/{case_a.id}")
        inaccessible = await client.get(f"/cases/{case_b.id}")
        unknown = await client.get(f"/cases/{uuid4()}")

    assert visible.status_code == 200
    assert inaccessible.status_code == unknown.status_code == 404
    assert inaccessible.json() == unknown.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_role_cannot_elevate_beyond_global_role() -> None:
    async with async_session_factory() as session:
        owner = make_user("owner-two", GlobalRole.CASE_OWNER)
        analyst = make_user("analyst-two", GlobalRole.ANALYST)
        session.add_all([owner, analyst])
        await session.flush()
        case = Case(
            case_code="AUTHZ-C",
            title="Intersection case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorization fixture",
        )
        session.add(case)
        await session.flush()
        await add_membership(
            session,
            case_id=case.id,
            user_id=analyst.id,
            role=GlobalRole.CASE_OWNER,
        )
        await session.commit()

        with pytest.raises(AuthorizationDenied):
            await authorize_case(analyst, case.id, Permission.CASE_UPDATE, session)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_can_repair_membership_but_does_not_bypass_case_read_scope() -> None:
    async with async_session_factory() as session:
        owner = make_user("owner-three", GlobalRole.CASE_OWNER)
        admin = make_user("admin-three", GlobalRole.ADMIN)
        session.add_all([owner, admin])
        await session.flush()
        case = Case(
            case_code="AUTHZ-D",
            title="Administrative repair case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorization fixture",
        )
        session.add(case)
        await session.commit()

        await authorize_case(admin, case.id, Permission.CASE_MEMBERSHIP_MANAGE, session)
        with pytest.raises(CaseNotFound):
            await authorize_case(admin, case.id, Permission.CASE_READ, session)
