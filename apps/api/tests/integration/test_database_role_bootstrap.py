from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa
from darknetra_api.config import get_settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
REPO_ROOT = Path(__file__).resolve().parents[4]


async def test_bootstrap_reconciles_deliberately_overprivileged_runtime_role() -> None:
    if os.getenv("DARKNETRA_RUN_BOOTSTRAP_TESTS") != "1":
        pytest.skip("set DARKNETRA_RUN_BOOTSTRAP_TESTS=1 for destructive role proof")
    compose_project = os.getenv("DARKNETRA_COMPOSE_PROJECT")
    runtime_password = os.getenv("DARKNETRA_POSTGRES_RUNTIME_PASSWORD")
    if not compose_project or not runtime_password:
        pytest.skip("isolated Compose project and runtime password are required")

    settings = get_settings()
    if not settings.database_owner_url:
        pytest.skip("DARKNETRA_DATABASE_OWNER_URL is required")
    engine = create_async_engine(settings.database_owner_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(
            sa.text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles "
                "WHERE rolname = 'darknetra_runtime_unintended_membership') THEN "
                "CREATE ROLE darknetra_runtime_unintended_membership NOLOGIN; "
                "END IF; END $$"
            )
        )
        await session.execute(
            sa.text(
                "ALTER ROLE darknetra_runtime SUPERUSER CREATEDB CREATEROLE "
                "REPLICATION BYPASSRLS NOINHERIT"
            )
        )
        await session.execute(
            sa.text(
                "GRANT darknetra_runtime_unintended_membership TO darknetra_runtime"
            )
        )
        await session.execute(
            sa.text(
                "CREATE TABLE IF NOT EXISTS runtime_owned_reconciliation_probe (id integer)"
            )
        )
        await session.execute(
            sa.text(
                "CREATE SCHEMA IF NOT EXISTS runtime_owned_reconciliation_schema "
                "AUTHORIZATION darknetra_runtime"
            )
        )
        await session.execute(
            sa.text(
                "ALTER TABLE runtime_owned_reconciliation_probe OWNER TO darknetra_runtime"
            )
        )
        await session.execute(
            sa.text("GRANT ALL PRIVILEGES ON custody_events TO darknetra_runtime")
        )
        await session.execute(
            sa.text(
                "DO $$ BEGIN EXECUTE format("
                "'GRANT CREATE, TEMPORARY ON DATABASE %I TO darknetra_runtime', "
                "current_database()); END $$"
            )
        )
        await session.execute(
            sa.text(
                "CREATE SCHEMA IF NOT EXISTS runtime_reconciliation_poison; "
                "CREATE TABLE IF NOT EXISTS runtime_reconciliation_poison.probe (id integer); "
                "CREATE SEQUENCE IF NOT EXISTS runtime_reconciliation_poison.probe_sequence; "
                "CREATE OR REPLACE FUNCTION runtime_reconciliation_poison.probe_function() "
                "RETURNS integer LANGUAGE sql AS 'SELECT 1'; "
                "GRANT ALL ON SCHEMA runtime_reconciliation_poison TO darknetra_runtime; "
                "GRANT ALL ON ALL TABLES IN SCHEMA runtime_reconciliation_poison "
                "TO darknetra_runtime; "
                "GRANT ALL ON ALL SEQUENCES IN SCHEMA runtime_reconciliation_poison "
                "TO darknetra_runtime; "
                "GRANT ALL ON ALL FUNCTIONS IN SCHEMA runtime_reconciliation_poison "
                "TO darknetra_runtime; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA runtime_reconciliation_poison "
                "GRANT ALL ON TABLES TO darknetra_runtime; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA runtime_reconciliation_poison "
                "GRANT ALL ON SEQUENCES TO darknetra_runtime; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA runtime_reconciliation_poison "
                "GRANT ALL ON FUNCTIONS TO darknetra_runtime"
            )
        )
        await session.commit()

    completed = await asyncio.to_thread(
        subprocess.run,
        [
            "docker",
            "compose",
            "-p",
            compose_project,
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.e2e.yml",
            "run",
            "--rm",
            "db-bootstrap",
        ],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    async with sessions() as session:
        attributes = (
            await session.execute(
                sa.text(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
                    "rolbypassrls, rolinherit FROM pg_roles "
                    "WHERE rolname = 'darknetra_runtime'"
                )
            )
        ).one()
        assert attributes == (False, False, False, False, False, True)
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM pg_auth_members membership "
                "JOIN pg_roles member_role ON member_role.oid = membership.member "
                "WHERE member_role.rolname = 'darknetra_runtime'"
            )
        ) == 0
        assert await session.scalar(
            sa.text(
                "SELECT tableowner = current_user FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename = 'runtime_owned_reconciliation_probe'"
            )
        ) is True
        assert await session.scalar(
            sa.text(
                "SELECT schema_owner = current_user FROM information_schema.schemata "
                "WHERE schema_name = 'runtime_owned_reconciliation_schema'"
            )
        ) is True
        custody_privileges = (
            await session.execute(
                sa.text(
                    "SELECT has_table_privilege('darknetra_runtime', "
                    "'custody_events', 'SELECT'), "
                    "has_table_privilege('darknetra_runtime', "
                    "'custody_events', 'INSERT'), "
                    "has_table_privilege('darknetra_runtime', "
                    "'custody_events', 'UPDATE'), "
                    "has_table_privilege('darknetra_runtime', "
                    "'custody_events', 'DELETE'), "
                    "has_table_privilege('darknetra_runtime', "
                    "'custody_events', 'TRUNCATE'), "
                    "has_schema_privilege('darknetra_runtime', 'public', 'CREATE')"
                )
            )
        ).one()
        assert custody_privileges == (True, True, False, False, False, False)
        database_privileges = (
            await session.execute(
                sa.text(
                    "SELECT has_database_privilege('darknetra_runtime', current_database(), "
                    "'CONNECT'), has_database_privilege('darknetra_runtime', current_database(), "
                    "'CREATE'), has_database_privilege('darknetra_runtime', current_database(), "
                    "'TEMPORARY')"
                )
            )
        ).one()
        assert database_privileges == (True, False, False)
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM ("
                "SELECT n.nspacl AS acl FROM pg_namespace n "
                "WHERE n.nspname = 'runtime_reconciliation_poison' "
                "UNION ALL SELECT c.relacl FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'runtime_reconciliation_poison' "
                "UNION ALL SELECT p.proacl FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'runtime_reconciliation_poison'"
                ") protected CROSS JOIN LATERAL aclexplode(protected.acl) acl "
                "JOIN pg_roles grantee ON grantee.oid = acl.grantee "
                "WHERE grantee.rolname = 'darknetra_runtime'"
            )
        ) == 0
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM pg_default_acl defaults "
                "CROSS JOIN LATERAL aclexplode(defaults.defaclacl) acl "
                "JOIN pg_roles grantee ON grantee.oid = acl.grantee "
                "LEFT JOIN pg_namespace namespace ON namespace.oid = defaults.defaclnamespace "
                "WHERE grantee.rolname = 'darknetra_runtime' "
                "AND namespace.nspname = 'runtime_reconciliation_poison'"
            )
        ) == 0
        await session.execute(sa.text("DROP TABLE runtime_owned_reconciliation_probe"))
        await session.execute(
            sa.text("DROP SCHEMA runtime_owned_reconciliation_schema")
        )
        await session.execute(
            sa.text("DROP ROLE darknetra_runtime_unintended_membership")
        )
        await session.execute(
            sa.text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA runtime_reconciliation_poison "
                "REVOKE ALL ON TABLES FROM darknetra_runtime; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA runtime_reconciliation_poison "
                "REVOKE ALL ON SEQUENCES FROM darknetra_runtime; "
                "ALTER DEFAULT PRIVILEGES IN SCHEMA runtime_reconciliation_poison "
                "REVOKE ALL ON FUNCTIONS FROM darknetra_runtime; "
                "DROP SCHEMA runtime_reconciliation_poison CASCADE"
            )
        )
        await session.commit()
    await engine.dispose()
