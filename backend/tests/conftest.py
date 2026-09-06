"""Tests use a dedicated PostgreSQL database; each test creates fresh synthetic actors."""

import base64
import os
import secrets
from pathlib import Path

import pytest
from dotenv import dotenv_values

from darknetra.config import Settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def test_settings(tmp_path):
    local = dotenv_values(ROOT / ".env")
    database_url = os.getenv("DARKNETRA_TEST_DATABASE_URL") or local.get(
        "DARKNETRA_TEST_DATABASE_URL"
    )
    if not database_url:
        pytest.skip("DARKNETRA_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    from sqlalchemy.engine import make_url

    if "test" not in (make_url(database_url).database or "").casefold():
        pytest.fail("Refusing integration tests against a database without 'test' in its name")
    return Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        vault_path=tmp_path / "vault",
        demo_mode=True,
        offline_mode=True,
        harness_mode="deterministic",
        scheduler_enabled=False,
        jwt_signing_key_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
        field_key_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
    )


@pytest.fixture
async def app(test_settings):
    from asgi_lifespan import LifespanManager

    from darknetra.main import create_app

    application = create_app(test_settings)
    async with LifespanManager(application, startup_timeout=30, shutdown_timeout=30):
        yield application


@pytest.fixture
async def client(app):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def actor_login(app, client):
    import asyncio
    from uuid import uuid4

    from darknetra.auth.models import User
    from darknetra.auth.passwords import hash_password

    async def login(role="INVESTIGATOR", forced=False):
        password = "SYNTHETIC fixture password 123"
        async with app.state.session_factory() as db:
            user = User(
                id=uuid4(),
                username=f"synthetic-{uuid4().hex}",
                display_name="SYNTHETIC Analyst",
                password_hash=await asyncio.to_thread(hash_password, password),
                global_role=role,
                must_change_password=forced,
            )
            db.add(user)
            await db.commit()
        response = await client.post(
            "/api/v1/auth/login", json={"username": user.username, "password": password}
        )
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = client.cookies["darknetra_csrf"]
        client.headers["Origin"] = app.state.settings.web_origin
        return user

    return login
