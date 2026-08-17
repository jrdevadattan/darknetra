from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import select

from darknetra_api.db.session import async_session_factory
from darknetra_api.main import app
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.user import User, utc_now
from darknetra_api.services.bootstrap import bootstrap_admin

ORIGIN = "http://localhost:3000"
INITIAL_PASSWORD = "Initial admin password 42"
NEW_PASSWORD = "Replacement admin password 84"


@pytest.fixture(autouse=True)
async def clean_auth_state() -> None:
    async with async_session_factory() as session:
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(AuthSession))
        await session.execute(sa.delete(User))
        await session.commit()
    yield
    async with async_session_factory() as session:
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(AuthSession))
        await session.execute(sa.delete(User))
        await session.commit()


async def seed_admin(username: str = "Investigator01") -> User:
    async with async_session_factory() as session:
        user = await bootstrap_admin(
            session,
            username=username,
            password=INITIAL_PASSWORD,
            display_name="Bootstrap Investigator",
            request_id=str(uuid4()),
        )
        await session.commit()
        await session.refresh(user)
        return user


def cookie_header(response: httpx.Response, name: str) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.lower().startswith(f"{name.lower()}="):
            return header
    raise AssertionError(f"missing Set-Cookie for {name}")


def max_age_from_cookie(header: str) -> int:
    for part in header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key.lower() == "max-age":
            return int(value)
    raise AssertionError(f"cookie missing Max-Age: {header}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_me_refresh_rotation_reuse_detection_and_cookie_security() -> None:
    await seed_admin()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "INVESTIGATOR01", "password": INITIAL_PASSWORD},
        )
        assert login.status_code == 200

        access_header = cookie_header(login, "darknetra_access")
        refresh_header = cookie_header(login, "darknetra_refresh")
        csrf_header = cookie_header(login, "darknetra_csrf")
        assert "httponly" in access_header.lower()
        assert "samesite=strict" in access_header.lower()
        assert "path=/" in access_header.lower()
        assert max_age_from_cookie(access_header) <= 900
        assert "httponly" in refresh_header.lower()
        assert "samesite=strict" in refresh_header.lower()
        assert "path=/api/v1/auth" in refresh_header.lower()
        assert max_age_from_cookie(refresh_header) <= 28800
        assert "httponly" not in csrf_header.lower()
        assert "samesite=strict" in csrf_header.lower()
        assert "path=/" in csrf_header.lower()

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "Investigator01"
        assert me.json()["must_change_password"] is True

        old_refresh = client.cookies.get("darknetra_refresh")
        old_csrf = client.cookies.get("darknetra_csrf")
        assert old_refresh and old_csrf

        missing_csrf = await client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
        assert missing_csrf.status_code == 403

        rotated = await client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": ORIGIN, "X-CSRF-Token": old_csrf},
        )
        assert rotated.status_code == 200
        new_refresh = client.cookies.get("darknetra_refresh")
        new_csrf = client.cookies.get("darknetra_csrf")
        assert new_refresh and new_refresh != old_refresh
        assert new_csrf and new_csrf != old_csrf

        client.cookies.set("darknetra_refresh", old_refresh, domain="api.test", path="/api/v1/auth")
        client.cookies.set("darknetra_csrf", old_csrf, domain="api.test", path="/")
        reuse = await client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": ORIGIN, "X-CSRF-Token": old_csrf},
        )
        assert reuse.status_code == 401

        client.cookies.set("darknetra_refresh", new_refresh, domain="api.test", path="/api/v1/auth")
        client.cookies.set("darknetra_csrf", new_csrf, domain="api.test", path="/")
        revoked_refresh = await client.post(
            "/api/v1/auth/refresh",
            headers={"Origin": ORIGIN, "X-CSRF-Token": new_csrf},
        )
        assert revoked_refresh.status_code == 401
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async with async_session_factory() as session:
        event_types = set((await session.scalars(select(AuditEvent.event_type))).all())
        assert "LOGIN_SUCCEEDED" in event_types
        assert "SESSION_REFRESHED" in event_types
        assert "REFRESH_TOKEN_REUSE_DETECTED" in event_types


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wrong_password_and_unknown_user_have_identical_failure_shape_and_lockout() -> None:
    user = await seed_admin()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        wrong = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "Investigator01", "password": "wrong password 123"},
        )
        unknown = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "does-not-exist", "password": "wrong password 123"},
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

        for _ in range(4):
            response = await client.post(
                "/api/v1/auth/login",
                headers={"Origin": ORIGIN},
                json={"username": "Investigator01", "password": "wrong password 123"},
            )
            assert response.status_code == 401

        locked = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "Investigator01", "password": INITIAL_PASSWORD},
        )
        assert locked.status_code == 401

    async with async_session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.failed_login_count == 5
        assert stored.locked_until is not None
        stored.locked_until = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        success = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "Investigator01", "password": INITIAL_PASSWORD},
        )
        assert success.status_code == 200

    async with async_session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.failed_login_count == 0
        assert stored.locked_until is None
        event_types = (await session.scalars(select(AuditEvent.event_type))).all()
        assert "ACCOUNT_TEMP_LOCKED" in event_types
        assert "LOGIN_FAILED" in event_types


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forced_password_change_and_logout_require_session_bound_csrf() -> None:
    await seed_admin()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "Investigator01", "password": INITIAL_PASSWORD},
        )
        assert login.status_code == 200
        csrf = client.cookies.get("darknetra_csrf")
        assert csrf

        no_csrf = await client.post(
            "/api/v1/auth/change-password",
            headers={"Origin": ORIGIN},
            json={"new_password": NEW_PASSWORD},
        )
        assert no_csrf.status_code == 403

        changed = await client.post(
            "/api/v1/auth/change-password",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
            json={"new_password": NEW_PASSWORD},
        )
        assert changed.status_code == 200
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["must_change_password"] is False

        wrong_csrf = await client.post(
            "/api/v1/auth/logout",
            headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong-token"},
        )
        assert wrong_csrf.status_code == 403

        logged_out = await client.post(
            "/api/v1/auth/logout",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        assert logged_out.status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async with async_session_factory() as session:
        event_types = (await session.scalars(select(AuditEvent.event_type))).all()
        assert "PASSWORD_CHANGED" in event_types
        assert "LOGOUT" in event_types


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_rejects_untrusted_browser_origin() -> None:
    await seed_admin()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"username": "Investigator01", "password": INITIAL_PASSWORD},
        )
        assert response.status_code == 403
