from __future__ import annotations

import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from darknetra_api.config import get_settings
from darknetra_api.models.case import Case
from darknetra_api.models.enums import CaseSensitivity, CaseStatus, GlobalRole
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceSensitiveValueKind,
    EvidenceSourceClass,
    EvidenceState,
)
from darknetra_api.models.user import User
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.services.evidence import build_evidence_derivation, build_sensitive_value
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
REPO_ROOT = Path(__file__).resolve().parents[4]
FINAL_EVIDENCE_REVISION = "c3f80a92d614"


def _migration_tests_enabled() -> bool:
    return os.getenv("DARKNETRA_RUN_MIGRATION_TESTS") == "1"


def _run_alembic(target: str, *, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", *target.split()],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success and completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)
    return completed


async def _owner_session_factory():
    settings = get_settings()
    if not settings.database_owner_url:
        pytest.skip("DARKNETRA_DATABASE_OWNER_URL is required")
    engine = create_async_engine(settings.database_owner_url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": secrets.token_bytes(32)},
        active_key_version="v1",
        blind_index_key=secrets.token_bytes(32),
    )


def _artifact(case: Case, owner: User, suffix: str) -> EvidenceArtifact:
    return EvidenceArtifact(
        case_id=case.id,
        source_class=EvidenceSourceClass.SYNTHETIC,
        source_type=f"migration-{suffix}",
        acquisition_method="authorized-fixture",
        collector_user_id=owner.id,
        captured_at=datetime.now(UTC),
        size_bytes=1,
        sha256=(suffix[0] * 64),
        sha512=(suffix[0] * 128),
        object_key=f"sha256/{suffix[0] * 2}/{suffix[0] * 64}",
        state=EvidenceState.PRESERVED,
    )


async def _clear(session) -> None:
    await session.execute(
        sa.text(
            "TRUNCATE custody_events, evidence_derivations, evidence_sensitive_values, "
            "evidence_artifacts, jobs, audit_events, case_membership_roles, "
            "case_memberships, cases, auth_sessions, users CASCADE"
        )
    )
    await session.commit()


async def test_populated_compatible_downgrade_and_upgrade_preserve_data() -> None:
    if not _migration_tests_enabled():
        pytest.skip("set DARKNETRA_RUN_MIGRATION_TESTS=1 for destructive migration proof")
    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        await _clear(session)
        owner = User(
            username="migration-compatible-owner",
            username_normalized="migration-compatible-owner",
            display_name="migration-compatible-owner",
            password_hash="not-used",
            global_roles=[GlobalRole.CASE_OWNER],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-MIGRATION-COMPATIBLE",
            title="Compatible migration data",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        parent = _artifact(case, owner, "a")
        child = _artifact(case, owner, "b")
        session.add_all([parent, child])
        await session.flush()
        value = build_sensitive_value(
            case_id=case.id,
            evidence_id=parent.id,
            kind=EvidenceSensitiveValueKind.CONTACT,
            plaintext="compatible@example.test",
            crypto=_crypto(),
        )
        derivation = build_evidence_derivation(
            case_id=case.id,
            parent_evidence_id=parent.id,
            child_evidence_id=child.id,
            transformation="extract",
            transformer_version="1",
            parameters={"member": "safe.txt"},
        )
        session.add_all([value, derivation])
        await session.commit()
        value_id = value.id
        derivation_id = derivation.id
    await engine.dispose()

    _run_alembic("downgrade b7c19a4e5d20")

    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        assert await session.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "b7c19a4e5d20"
        )
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname = 'darknetra_derivation_parameters_digest'"
            )
        ) == 0
        assert await session.scalar(
            sa.text("SELECT count(*) FROM evidence_sensitive_values WHERE id = :id").bindparams(
                id=value_id
            )
        ) == 1
    await engine.dispose()

    _run_alembic("upgrade head")

    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        assert await session.scalar(
            sa.text("SELECT count(*) FROM evidence_sensitive_values WHERE id = :id").bindparams(
                id=value_id
            )
        ) == 1
        digest = await session.scalar(
            sa.text(
                "SELECT parameters_digest FROM evidence_derivations WHERE id = :id"
            ).bindparams(id=derivation_id)
        )
        assert isinstance(digest, str) and len(digest) == 64
        await _clear(session)
    await engine.dispose()


async def test_incompatible_downgrade_refuses_atomically_and_preserves_upgraded_data() -> None:
    if not _migration_tests_enabled():
        pytest.skip("set DARKNETRA_RUN_MIGRATION_TESTS=1 for destructive migration proof")
    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        await _clear(session)
        owner = User(
            username="migration-incompatible-owner",
            username_normalized="migration-incompatible-owner",
            display_name="migration-incompatible-owner",
            password_hash="not-used",
            global_roles=[GlobalRole.CASE_OWNER],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-MIGRATION-INCOMPATIBLE",
            title="Incompatible migration data",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        parent = _artifact(case, owner, "c")
        child = _artifact(case, owner, "d")
        session.add_all([parent, child])
        await session.flush()
        crypto = _crypto()
        repeated = [
            build_sensitive_value(
                case_id=case.id,
                evidence_id=parent.id,
                kind=EvidenceSensitiveValueKind.CONTACT,
                plaintext=f"repeated-{number}@example.test",
                crypto=crypto,
            )
            for number in (1, 2)
        ]
        lineage = [
            build_evidence_derivation(
                case_id=case.id,
                parent_evidence_id=parent.id,
                child_evidence_id=child.id,
                transformation="extract",
                transformer_version="1",
                parameters={"member": member},
            )
            for member in ("first.txt", "second.txt")
        ]
        session.add_all([*repeated, *lineage])
        await session.commit()
        repeated_ids = [row.id for row in repeated]
    await engine.dispose()

    refused = _run_alembic("downgrade b7c19a4e5d20", expect_success=False)
    assert refused.returncode != 0
    assert "cannot downgrade evidence invariants" in refused.stdout + refused.stderr

    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        assert await session.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        ) == FINAL_EVIDENCE_REVISION
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'evidence_derivations' "
                "AND column_name = 'parameters_digest'"
            )
        ) == 1
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM evidence_sensitive_values WHERE id = ANY(:ids)"
            ).bindparams(ids=repeated_ids)
        ) == 2
        assert await session.scalar(sa.text("SELECT count(*) FROM evidence_derivations")) == 2
        await _clear(session)
    await engine.dispose()


async def test_historical_b7_populated_database_upgrades_to_new_head() -> None:
    if not _migration_tests_enabled():
        pytest.skip("set DARKNETRA_RUN_MIGRATION_TESTS=1 for destructive migration proof")

    _run_alembic("downgrade base")
    _run_alembic("upgrade b7c19a4e5d20")

    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        owner = User(
            username="historical-b7-owner",
            username_normalized="historical-b7-owner",
            display_name="historical-b7-owner",
            password_hash="not-used",
            global_roles=[GlobalRole.CASE_OWNER],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-HISTORICAL-B7",
            title="Historical b7 populated upgrade",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        parent = _artifact(case, owner, "e")
        child = _artifact(case, owner, "f")
        session.add_all([parent, child])
        await session.flush()
        value = build_sensitive_value(
            case_id=case.id,
            evidence_id=parent.id,
            kind=EvidenceSensitiveValueKind.CONTACT,
            plaintext="historical@example.test",
            crypto=_crypto(),
        )
        derivation = build_evidence_derivation(
            case_id=case.id,
            parent_evidence_id=parent.id,
            child_evidence_id=child.id,
            transformation="historical-extract",
            transformer_version="1",
            parameters={"nested": [1.0, {"large": 1e20}]},
        )
        session.add_all([value, derivation])
        await session.commit()
        value_id = value.id
        derivation_id = derivation.id
    await engine.dispose()

    _run_alembic("upgrade head")

    engine, sessions = await _owner_session_factory()
    async with sessions() as session:
        assert await session.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            FINAL_EVIDENCE_REVISION
        )
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname IN ('darknetra_canonical_jsonb', "
                "'darknetra_derivation_parameters_digest')"
            )
        ) == 2
        assert await session.scalar(
            sa.text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname IN ('custody_events_reject_runtime_truncate', "
                "'evidence_manifest_immutable') AND NOT tgisinternal"
            )
        ) == 2
        assert await session.scalar(
            sa.text("SELECT count(*) FROM evidence_sensitive_values WHERE id = :id").bindparams(
                id=value_id
            )
        ) == 1
        assert await session.scalar(
            sa.text(
                "SELECT parameters_digest = "
                "darknetra_derivation_parameters_digest(parameters_json) "
                "FROM evidence_derivations WHERE id = :id"
            ).bindparams(id=derivation_id)
        ) is True
        assert await session.scalar(
            sa.text(
                "SELECT has_table_privilege('darknetra_runtime', "
                "'custody_events', 'SELECT, INSERT')"
            )
        ) is True
        assert await session.scalar(
            sa.text(
                "SELECT has_table_privilege('darknetra_runtime', "
                "'custody_events', 'UPDATE, DELETE, TRUNCATE')"
            )
        ) is False
        await _clear(session)
    await engine.dispose()
