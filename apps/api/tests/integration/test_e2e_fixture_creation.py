import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.passwords import verify_password

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "create_e2e_fixture.py"

ANALYST_A_ID = UUID("00000000-0000-4000-8000-0000000000a1")
ANALYST_B_ID = UUID("00000000-0000-4000-8000-0000000000b1")
BOOTSTRAP_ID = UUID("00000000-0000-4000-8000-0000000000c1")
CASE_A_ID = UUID("00000000-0000-4000-8000-000000000ca1")
CASE_B_ID = UUID("00000000-0000-4000-8000-000000000cb1")

ANALYST_A_PASSWORD = "Synthetic-A-Password-42!"
ANALYST_B_PASSWORD = "Synthetic-B-Password-42!"
BOOTSTRAP_PASSWORD = "Synthetic-Bootstrap-42!"


def e2e_database_url() -> str:
    value = os.getenv("DARKNETRA_E2E_DATABASE_URL")
    if not value:
        pytest.skip("DARKNETRA_E2E_DATABASE_URL is required for isolated fixture integration tests")
    return value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fixture_cli_creates_deterministic_isolated_state_without_secret_output() -> None:
    database_url = e2e_database_url()
    env = os.environ.copy()
    env.update(
        {
            "DARKNETRA_ENVIRONMENT": "test",
            "DARKNETRA_DATABASE_URL": database_url,
            "DARKNETRA_E2E_ANALYST_A_PASSWORD": ANALYST_A_PASSWORD,
            "DARKNETRA_E2E_ANALYST_B_PASSWORD": ANALYST_B_PASSWORD,
            "DARKNETRA_E2E_BOOTSTRAP_PASSWORD": BOOTSTRAP_PASSWORD,
        }
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "users": {
            "analyst_a": {"id": str(ANALYST_A_ID), "username": "e2e.analyst.a"},
            "analyst_b": {"id": str(ANALYST_B_ID), "username": "e2e.analyst.b"},
            "bootstrap": {"id": str(BOOTSTRAP_ID), "username": "e2e.bootstrap"},
        },
        "cases": {
            "analyst_a": {"id": str(CASE_A_ID), "case_code": "E2E-A-001"},
            "analyst_b": {"id": str(CASE_B_ID), "case_code": "E2E-B-001"},
        },
    }
    for secret in (ANALYST_A_PASSWORD, ANALYST_B_PASSWORD, BOOTSTRAP_PASSWORD):
        assert secret not in result.stdout
        assert secret not in result.stderr
    assert "password_hash" not in result.stdout
    assert "refresh_token" not in result.stdout

    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            analyst_a = await session.get(User, ANALYST_A_ID)
            analyst_b = await session.get(User, ANALYST_B_ID)
            bootstrap = await session.get(User, BOOTSTRAP_ID)
            assert analyst_a is not None
            assert analyst_b is not None
            assert bootstrap is not None

            assert analyst_a.username == "e2e.analyst.a"
            assert analyst_b.username == "e2e.analyst.b"
            assert bootstrap.username == "e2e.bootstrap"
            assert set(analyst_a.global_roles) == {GlobalRole.CASE_OWNER, GlobalRole.ANALYST}
            assert set(analyst_b.global_roles) == {GlobalRole.CASE_OWNER, GlobalRole.ANALYST}
            assert bootstrap.global_roles == [GlobalRole.ADMIN]
            assert analyst_a.must_change_password is False
            assert analyst_b.must_change_password is False
            assert bootstrap.must_change_password is True
            assert verify_password(ANALYST_A_PASSWORD, analyst_a.password_hash)
            assert verify_password(ANALYST_B_PASSWORD, analyst_b.password_hash)
            assert verify_password(BOOTSTRAP_PASSWORD, bootstrap.password_hash)

            case_a = await session.get(Case, CASE_A_ID)
            case_b = await session.get(Case, CASE_B_ID)
            assert case_a is not None and case_a.owner_user_id == ANALYST_A_ID
            assert case_b is not None and case_b.owner_user_id == ANALYST_B_ID

            memberships = list(
                (
                    await session.scalars(
                        sa.select(CaseMembership).order_by(
                            CaseMembership.case_id.asc(), CaseMembership.user_id.asc()
                        )
                    )
                ).all()
            )
            assert {(item.case_id, item.user_id) for item in memberships} == {
                (CASE_A_ID, ANALYST_A_ID),
                (CASE_B_ID, ANALYST_B_ID),
            }

            membership_roles = list((await session.scalars(sa.select(CaseMembershipRole))).all())
            roles_by_membership: dict[UUID, set[GlobalRole]] = {}
            for item in membership_roles:
                roles_by_membership.setdefault(item.membership_id, set()).add(item.role)
            assert all(
                roles == {GlobalRole.CASE_OWNER, GlobalRole.ANALYST}
                for roles in roles_by_membership.values()
            )
    finally:
        await engine.dispose()
