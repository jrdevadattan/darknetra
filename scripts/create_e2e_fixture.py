from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from urllib.parse import urlparse
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseSensitivity, GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.passwords import PasswordPolicyError, hash_password, validate_password_policy

REQUIRED_CREDENTIAL_VARIABLES = (
    "DARKNETRA_E2E_ANALYST_A_PASSWORD",
    "DARKNETRA_E2E_ANALYST_B_PASSWORD",
    "DARKNETRA_E2E_BOOTSTRAP_PASSWORD",
)

ANALYST_A_ID = UUID("00000000-0000-4000-8000-0000000000a1")
ANALYST_B_ID = UUID("00000000-0000-4000-8000-0000000000b1")
BOOTSTRAP_ID = UUID("00000000-0000-4000-8000-0000000000c1")
CASE_A_ID = UUID("00000000-0000-4000-8000-000000000ca1")
CASE_B_ID = UUID("00000000-0000-4000-8000-000000000cb1")
MEMBERSHIP_A_ID = UUID("00000000-0000-4000-8000-000000000da1")
MEMBERSHIP_B_ID = UUID("00000000-0000-4000-8000-000000000db1")


class FixtureSafetyError(RuntimeError):
    pass


def _database_name(database_url: str) -> str:
    parsed = urlparse(database_url)
    return parsed.path.lstrip("/").split("/", maxsplit=1)[0]


def validate_fixture_environment(environment: Mapping[str, str]) -> None:
    if environment.get("DARKNETRA_ENVIRONMENT") != "test":
        raise FixtureSafetyError("fixture creation requires DARKNETRA_ENVIRONMENT=test")

    database_url = environment.get("DARKNETRA_DATABASE_URL", "")
    database_name = _database_name(database_url)
    if not database_name or "test" not in database_name.lower():
        raise FixtureSafetyError(
            "fixture creation requires a clearly test-scoped database name containing 'test'"
        )

    missing = [name for name in REQUIRED_CREDENTIAL_VARIABLES if not environment.get(name)]
    if missing:
        raise FixtureSafetyError(
            "missing synthetic credential environment variables: " + ", ".join(missing)
        )


def _validated_password(environment: Mapping[str, str], variable: str, *, username: str) -> str:
    password = environment[variable]
    try:
        validate_password_policy(password, username=username)
    except PasswordPolicyError as exc:
        raise FixtureSafetyError(f"{variable} violates the password policy: {exc}") from exc
    return password


async def _reset_plan02_state(session: AsyncSession) -> None:
    await session.execute(sa.delete(CaseMembershipRole))
    await session.execute(sa.delete(CaseMembership))
    await session.execute(sa.delete(AuditEvent))
    await session.execute(sa.delete(Case))
    await session.execute(sa.delete(AuthSession))
    await session.execute(sa.delete(User))
    await session.flush()


async def create_fixture(environment: Mapping[str, str]) -> dict[str, object]:
    validate_fixture_environment(environment)
    database_url = environment["DARKNETRA_DATABASE_URL"]
    analyst_a_password = _validated_password(
        environment,
        "DARKNETRA_E2E_ANALYST_A_PASSWORD",
        username="e2e.analyst.a",
    )
    analyst_b_password = _validated_password(
        environment,
        "DARKNETRA_E2E_ANALYST_B_PASSWORD",
        username="e2e.analyst.b",
    )
    bootstrap_password = _validated_password(
        environment,
        "DARKNETRA_E2E_BOOTSTRAP_PASSWORD",
        username="e2e.bootstrap",
    )

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with sessions() as session:
            await _reset_plan02_state(session)

            analyst_a = User(
                id=ANALYST_A_ID,
                username="e2e.analyst.a",
                username_normalized="e2e.analyst.a",
                display_name="E2E Analyst A",
                password_hash=hash_password(analyst_a_password),
                global_roles=[GlobalRole.CASE_OWNER, GlobalRole.ANALYST],
                is_active=True,
                must_change_password=False,
            )
            analyst_b = User(
                id=ANALYST_B_ID,
                username="e2e.analyst.b",
                username_normalized="e2e.analyst.b",
                display_name="E2E Analyst B",
                password_hash=hash_password(analyst_b_password),
                global_roles=[GlobalRole.CASE_OWNER, GlobalRole.ANALYST],
                is_active=True,
                must_change_password=False,
            )
            bootstrap = User(
                id=BOOTSTRAP_ID,
                username="e2e.bootstrap",
                username_normalized="e2e.bootstrap",
                display_name="E2E Bootstrap Administrator",
                password_hash=hash_password(bootstrap_password),
                global_roles=[GlobalRole.ADMIN],
                is_active=True,
                must_change_password=True,
            )
            session.add_all([analyst_a, analyst_b, bootstrap])
            await session.flush()

            case_a = Case(
                id=CASE_A_ID,
                case_code="E2E-A-001",
                title="E2E Analyst A synthetic case",
                sensitivity=CaseSensitivity.STANDARD,
                owner_user_id=ANALYST_A_ID,
                source_authority_summary="Authorized synthetic E2E fixture for Analyst A",
            )
            case_b = Case(
                id=CASE_B_ID,
                case_code="E2E-B-001",
                title="E2E Analyst B synthetic case",
                sensitivity=CaseSensitivity.RESTRICTED,
                owner_user_id=ANALYST_B_ID,
                source_authority_summary="Authorized synthetic E2E fixture for Analyst B",
            )
            session.add_all([case_a, case_b])
            await session.flush()

            membership_a = CaseMembership(
                id=MEMBERSHIP_A_ID,
                case_id=CASE_A_ID,
                user_id=ANALYST_A_ID,
            )
            membership_b = CaseMembership(
                id=MEMBERSHIP_B_ID,
                case_id=CASE_B_ID,
                user_id=ANALYST_B_ID,
            )
            session.add_all([membership_a, membership_b])
            await session.flush()
            session.add_all(
                [
                    CaseMembershipRole(
                        membership_id=MEMBERSHIP_A_ID,
                        role=GlobalRole.CASE_OWNER,
                    ),
                    CaseMembershipRole(
                        membership_id=MEMBERSHIP_A_ID,
                        role=GlobalRole.ANALYST,
                    ),
                    CaseMembershipRole(
                        membership_id=MEMBERSHIP_B_ID,
                        role=GlobalRole.CASE_OWNER,
                    ),
                    CaseMembershipRole(
                        membership_id=MEMBERSHIP_B_ID,
                        role=GlobalRole.ANALYST,
                    ),
                ]
            )
            await session.commit()
    finally:
        await engine.dispose()

    return {
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


def main() -> int:
    try:
        payload = asyncio.run(create_fixture(os.environ))
    except FixtureSafetyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - exercised by workflow diagnostics
        print(f"fixture creation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
