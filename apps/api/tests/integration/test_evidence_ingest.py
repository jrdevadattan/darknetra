from __future__ import annotations

import io
import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path
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
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.enums import CaseSensitivity, CaseStatus, GlobalRole, JobStatus
from darknetra_api.models.evidence import EvidenceArtifact, EvidenceSensitiveValue
from darknetra_api.models.job import AnalysisJob
from darknetra_api.models.user import User, utc_now
from darknetra_api.policy.ingestion import EvidenceSourceMetadata, preserve_upload
from darknetra_api.security.csrf import generate_csrf_token, hash_csrf_token
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.security.tokens import (
    REFRESH_TOKEN_LIFETIME,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from darknetra_api.services.evidence_ingest import persist_preserved_upload
from darknetra_api.storage.local import LocalObjectStore
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": secrets.token_bytes(32)},
        active_key_version="v1",
        blind_index_key=secrets.token_bytes(32),
    )


async def clear_state() -> None:
    settings = get_settings()
    owner_engine = create_async_engine(settings.database_owner_url or settings.database_url)
    sessions = async_sessionmaker(owner_engine, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(
            sa.text(
                "TRUNCATE custody_events, evidence_derivations, evidence_sensitive_values, "
                "evidence_artifacts, jobs, audit_events, case_membership_roles, "
                "case_memberships, cases, auth_sessions, users CASCADE"
            )
        )
        await session.commit()
    await owner_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_database() -> None:
    await clear_state()
    yield
    await clear_state()


def user(name: str, role: GlobalRole) -> User:
    return User(
        username=name,
        username_normalized=name,
        display_name=name,
        password_hash="not-used",
        global_roles=[role],
        is_active=True,
        must_change_password=False,
    )


async def membership(session, case: Case, actor: User, role: GlobalRole) -> None:
    row = CaseMembership(case_id=case.id, user_id=actor.id)
    session.add(row)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=row.id, role=role))


async def issue_session(session, actor: User) -> tuple[str, str]:
    csrf = generate_csrf_token()
    auth_session = AuthSession(
        user_id=actor.id,
        refresh_token_hash=hash_refresh_token(generate_refresh_token()),
        csrf_token_hash=hash_csrf_token(csrf),
        expires_at=utc_now() + REFRESH_TOKEN_LIFETIME,
    )
    session.add(auth_session)
    await session.flush()
    access = create_access_token(
        user_id=actor.id,
        session_id=auth_session.id,
        signing_key_b64=get_settings().require_jwt_signing_key_b64(),
    )
    return access, csrf


def source_metadata(locator: str) -> EvidenceSourceMetadata:
    return EvidenceSourceMetadata.model_validate(
        {
            "source_class": "PUBLIC_OBSERVATION",
            "source_type": "TEXT",
            "acquisition_method": "authorized fixture",
            "captured_at": datetime.now(UTC),
            "source_locator": locator,
            "authority_reference": "integration authority",
            "protected_note": "integration protected note",
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_transaction_is_atomic_and_publish_observes_committed_pending_job(
    tmp_path: Path,
) -> None:
    store = LocalObjectStore(tmp_path)
    preserved = preserve_upload(
        stream=io.BytesIO(b"authoritative text\nsecond line\n"),
        object_store=store,
        metadata=source_metadata("https://example.test/transaction"),
        filename="capture.txt",
        declared_content_type="text/plain",
        max_bytes=1024,
    )
    async with async_session_factory() as session:
        collector = user("ingest-transaction-collector", GlobalRole.COLLECTOR)
        session.add(collector)
        await session.flush()
        case = Case(
            case_code="INGEST-TRANSACTION",
            title="Ingestion transaction",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=collector.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.commit()
        case_id = case.id
        collector_id = collector.id

    observed_payloads: list[dict[str, str]] = []

    async def observe_after_commit(payload: dict[str, str]) -> None:
        async with async_session_factory() as observer:
            visible_job = await observer.get(AnalysisJob, payload["job_id"])
            assert visible_job is not None
            assert visible_job.status is JobStatus.PENDING
        observed_payloads.append(payload)

    async with async_session_factory() as session:
        result = await persist_preserved_upload(
            session,
            case_id=case_id,
            actor_user_id=collector_id,
            metadata=source_metadata("https://example.test/transaction"),
            preserved=preserved,
            crypto=crypto(),
            request_id="integration-transaction",
            publisher=observe_after_commit,
        )

    async with async_session_factory() as session:
        artifact = await session.get(EvidenceArtifact, result.evidence_id)
        values = (
            await session.scalars(
                sa.select(EvidenceSensitiveValue).where(
                    EvidenceSensitiveValue.evidence_id == result.evidence_id
                )
            )
        ).all()
        audit = await session.scalar(
            sa.select(AuditEvent).where(AuditEvent.resource_id == str(result.evidence_id))
        )
        custody = await session.scalar(
            sa.select(CustodyEvent).where(CustodyEvent.evidence_id == result.evidence_id)
        )
        job = await session.get(AnalysisJob, result.job_id)

    assert artifact is not None and artifact.object_key == preserved.stored.object_key
    assert len(values) == 3
    assert sum(value.blind_index is not None for value in values) == 1
    assert audit is not None and audit.event_type == "EVIDENCE_INGESTED"
    assert custody is not None and custody.action == "CUSTODY_CREATED"
    assert job is not None and job.idempotency_key == f"ingest:{result.evidence_id}:v1"
    assert observed_payloads == [
        {
            "job_id": str(result.job_id),
            "case_id": str(case_id),
            "evidence_id": str(result.evidence_id),
            "pipeline_version": "v1",
        }
    ]
    with store.open(preserved.stored.object_key) as stored_file:
        assert stored_file.read() == b"authoritative text\nsecond line\n"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_metadata_conflict_rolls_back_every_row_but_retains_promoted_orphan(
    tmp_path: Path,
) -> None:
    store = LocalObjectStore(tmp_path)
    async with async_session_factory() as session:
        collector = user("ingest-orphan-collector", GlobalRole.COLLECTOR)
        session.add(collector)
        await session.flush()
        case = Case(
            case_code="INGEST-ORPHAN",
            title="Ingestion orphan",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=collector.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.commit()
        case_id, collector_id = case.id, collector.id

    first_metadata = source_metadata("https://example.test/duplicate-locator")
    crypto_service = crypto()
    first = preserve_upload(
        stream=io.BytesIO(b"first retained object\n"),
        object_store=store,
        metadata=first_metadata,
        filename="first.txt",
        declared_content_type="text/plain",
        max_bytes=1024,
    )
    async with async_session_factory() as session:
        await persist_preserved_upload(
            session,
            case_id=case_id,
            actor_user_id=collector_id,
            metadata=first_metadata,
            preserved=first,
            crypto=crypto_service,
            request_id="first",
            publisher=lambda payload: None,
        )

    orphan = preserve_upload(
        stream=io.BytesIO(b"second orphaned object\n"),
        object_store=store,
        metadata=first_metadata,
        filename="second.txt",
        declared_content_type="text/plain",
        max_bytes=1024,
    )
    async with async_session_factory() as session:
        with pytest.raises(IntegrityError) as caught:
            await persist_preserved_upload(
                session,
                case_id=case_id,
                actor_user_id=collector_id,
                metadata=first_metadata,
                preserved=orphan,
                crypto=crypto_service,
                request_id="conflict",
                publisher=lambda payload: None,
            )

    assert "SQL parameters hidden due to hide_parameters=True" in str(caught.value)

    async with async_session_factory() as session:
        assert await session.scalar(sa.select(sa.func.count()).select_from(EvidenceArtifact)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(AuditEvent)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(CustodyEvent)) == 1
        assert await session.scalar(sa.select(sa.func.count()).select_from(AnalysisJob)) == 1
    with store.open(orphan.stored.object_key) as orphan_file:
        assert orphan_file.read() == b"second orphaned object\n"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_upload_route_enforces_auth_csrf_role_and_case_scope(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = LocalObjectStore(tmp_path)
    async with async_session_factory() as session:
        collector = user("route-collector", GlobalRole.COLLECTOR)
        viewer = user("route-viewer", GlobalRole.VIEWER)
        session.add_all([collector, viewer])
        await session.flush()
        visible = Case(
            case_code="INGEST-ROUTE-A",
            title="Visible upload case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=collector.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        hidden = Case(
            case_code="INGEST-ROUTE-B",
            title="Hidden upload case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=collector.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add_all([visible, hidden])
        await session.flush()
        await membership(session, visible, collector, GlobalRole.COLLECTOR)
        await membership(session, visible, viewer, GlobalRole.VIEWER)
        collector_access, collector_csrf = await issue_session(session, collector)
        viewer_access, viewer_csrf = await issue_session(session, viewer)
        await session.commit()
        visible_id, hidden_id = visible.id, hidden.id

    app.state.runtime_settings = get_settings()
    app.state.sensitive_field_crypto = crypto()
    app.state.evidence_object_store = store
    app.state.ingest_publisher = lambda payload: None
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    def request_parts(locator: str):
        metadata = {
            "source_class": "PUBLIC_OBSERVATION",
            "source_type": "TEXT",
            "acquisition_method": "ASGI integration",
            "captured_at": "2026-08-25T10:30:00Z",
            "source_locator": locator,
            "authority_reference": "route authority",
        }
        return {
            "data": {"metadata": json.dumps(metadata)},
            "files": {"file": ("capture.txt", b"route text\nsecond line\n", "text/plain")},
        }

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
            unauthenticated = await client.post(
                f"/api/v1/cases/{visible_id}/evidence",
                **request_parts("https://example.test/unauthenticated"),
            )
            assert unauthenticated.status_code == 401

            client.cookies.set("darknetra_access", collector_access, domain="api.test", path="/")
            missing_csrf = await client.post(
                f"/api/v1/cases/{visible_id}/evidence",
                **request_parts("https://example.test/missing-csrf"),
            )
            assert missing_csrf.status_code == 403

            client.cookies.set("darknetra_access", viewer_access, domain="api.test", path="/")
            viewer_denied = await client.post(
                f"/api/v1/cases/{visible_id}/evidence",
                headers={"X-CSRF-Token": viewer_csrf},
                **request_parts("https://example.test/viewer"),
            )
            assert viewer_denied.status_code == 403

            client.cookies.set("darknetra_access", collector_access, domain="api.test", path="/")
            hidden_response = await client.post(
                f"/api/v1/cases/{hidden_id}/evidence",
                headers={"X-CSRF-Token": collector_csrf},
                **request_parts("https://example.test/hidden"),
            )
            unknown_response = await client.post(
                f"/api/v1/cases/{uuid4()}/evidence",
                headers={"X-CSRF-Token": collector_csrf},
                **request_parts("https://example.test/unknown"),
            )
            assert hidden_response.status_code == unknown_response.status_code == 404
            assert hidden_response.json() == unknown_response.json()

            accepted = await client.post(
                f"/api/v1/cases/{visible_id}/evidence",
                headers={"X-CSRF-Token": collector_csrf},
                **request_parts("https://example.test/accepted"),
            )
            assert accepted.status_code == 202
            assert accepted.json()["job"]["status"] == "PENDING"

            caplog.clear()
            caplog.set_level(logging.ERROR, logger="darknetra_api.routes.evidence")
            conflict = await client.post(
                f"/api/v1/cases/{visible_id}/evidence",
                headers={"X-CSRF-Token": collector_csrf},
                **request_parts("https://example.test/accepted"),
            )
            assert conflict.status_code == 503
            assert conflict.json() == {
                "detail": {"code": "EVIDENCE_PERSISTENCE_FAILED"}
            }
            rendered = conflict.text + caplog.text
            for forbidden in (
                "https://example.test/accepted",
                "route authority",
                "ciphertext",
                "blind_index",
                "object_key",
                str(tmp_path),
                "redis://",
            ):
                assert forbidden not in rendered
            assert "code=EVIDENCE_PERSISTENCE_FAILED" in caplog.text
            assert "error_type=IntegrityError" in caplog.text

        async with async_session_factory() as session:
            assert await session.scalar(
                sa.select(sa.func.count()).select_from(EvidenceArtifact)
            ) == 1
            assert await session.scalar(
                sa.select(sa.func.count()).select_from(EvidenceSensitiveValue)
            ) == 2
            assert await session.scalar(
                sa.select(sa.func.count()).select_from(AuditEvent)
            ) == 1
            assert await session.scalar(
                sa.select(sa.func.count()).select_from(CustodyEvent)
            ) == 1
            assert await session.scalar(
                sa.select(sa.func.count()).select_from(AnalysisJob)
            ) == 1
    finally:
        del app.state.evidence_object_store
        del app.state.ingest_publisher
        del app.state.runtime_settings
        del app.state.sensitive_field_crypto
