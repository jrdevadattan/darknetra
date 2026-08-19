from __future__ import annotations

import importlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.authz.policy import CaseNotFound
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.enums import CaseSensitivity, GlobalRole
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceDerivation,
    EvidenceSourceClass,
    EvidenceState,
)
from darknetra_api.models.job import Job, JobState
from darknetra_api.models.user import User
from darknetra_api.policy.ingestion import (
    EvidenceSourceMetadata,
    IngestionLimits,
    MediaTypeMismatch,
    UploadSizeExceeded,
)
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.storage.local import LocalObjectStore


def preservation_service():
    try:
        return importlib.import_module("darknetra_api.services.evidence_ingest")
    except ModuleNotFoundError as exc:
        raise AssertionError("evidence preservation service is not implemented") from exc


class ReadTrackingStream(BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.read_calls = 0

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        return super().read(size)


async def _clean() -> None:
    async with async_session_factory() as session:
        await session.execute(sa.delete(CustodyEvent))
        await session.execute(sa.delete(EvidenceDerivation))
        await session.execute(sa.delete(EvidenceArtifact))
        await session.execute(sa.delete(Job))
        await session.execute(sa.delete(CaseMembershipRole))
        await session.execute(sa.delete(CaseMembership))
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(Case))
        await session.execute(sa.delete(AuthSession))
        await session.execute(sa.delete(User))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_database() -> None:
    await _clean()
    yield
    await _clean()


async def _seed_authorized_case() -> tuple[User, Case]:
    async with async_session_factory() as session:
        suffix = uuid4().hex[:10]
        owner = User(
            username=f"preserver-{suffix}",
            username_normalized=f"preserver-{suffix}",
            display_name="Synthetic Evidence Preserver",
            password_hash="unused",
            global_roles=[GlobalRole.CASE_OWNER],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code=f"PRE-{suffix.upper()}",
            title="Authorized synthetic preservation test",
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Authorized synthetic fixture",
        )
        session.add(case)
        await session.flush()
        membership = CaseMembership(case_id=case.id, user_id=owner.id)
        session.add(membership)
        await session.flush()
        session.add(
            CaseMembershipRole(
                membership_id=membership.id,
                role=GlobalRole.CASE_OWNER,
            )
        )
        await session.commit()
        await session.refresh(owner)
        await session.refresh(case)
        return owner, case


async def _seed_outsider() -> User:
    async with async_session_factory() as session:
        suffix = uuid4().hex[:10]
        user = User(
            username=f"outsider-{suffix}",
            username_normalized=f"outsider-{suffix}",
            display_name="Synthetic Outsider",
            password_hash="unused",
            global_roles=[GlobalRole.CASE_OWNER],
            is_active=True,
            must_change_password=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def _metadata() -> EvidenceSourceMetadata:
    return EvidenceSourceMetadata(
        source_class=EvidenceSourceClass.SYNTHETIC,
        source_type="synthetic.fixture",
        acquisition_method="authorized_test_generation",
        captured_at=datetime.now(UTC),
        original_timezone="UTC",
        source_locator="https://example.invalid/authorized-fixture",
        authority_reference="SYNTHETIC-AUTH-001",
        notes="Restricted synthetic preservation note",
        tool_name="pytest",
        tool_version="1.0",
    )


def _crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": b"A" * 32},
        active_key_version="v1",
        blind_index_key=b"B" * 32,
    )


async def _artifact_count() -> int:
    async with async_session_factory() as session:
        return int(
            (
                await session.execute(sa.select(sa.func.count(EvidenceArtifact.id)))
            ).scalar_one()
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preservation_creates_manifest_custody_audit_and_durable_job(
    tmp_path: Path,
) -> None:
    service = preservation_service()
    actor, case = await _seed_authorized_case()
    payload = b"authorized synthetic evidence\n"
    store = LocalObjectStore(tmp_path / "vault")
    request_id = str(uuid4())

    async with async_session_factory() as session:
        result = await service.preserve_uploaded_evidence(
            session=session,
            actor=actor,
            case_id=case.id,
            stream=BytesIO(payload),
            metadata=_metadata(),
            declared_media_type="text/plain; charset=utf-8",
            content_length=str(len(payload)),
            object_store=store,
            crypto=_crypto(),
            request_id=request_id,
            pipeline_version="v1",
        )
        evidence_id = result.artifact.id
        job_id = result.job.id
        await session.commit()

    async with async_session_factory() as session:
        artifact = await session.get(EvidenceArtifact, evidence_id)
        job = await session.get(Job, job_id)
        custody = (
            await session.scalars(
                sa.select(CustodyEvent).where(CustodyEvent.evidence_id == evidence_id)
            )
        ).all()
        audits = (
            await session.scalars(
                sa.select(AuditEvent).where(
                    AuditEvent.resource_type == "evidence",
                    AuditEvent.resource_id == str(evidence_id),
                )
            )
        ).all()

        assert artifact is not None
        assert artifact.state is EvidenceState.PRESERVED
        assert artifact.sha256 == result.stored_object.sha256
        assert artifact.size_bytes == len(payload)
        assert artifact.media_type == "text/plain"
        assert artifact.source_locator_ciphertext is not None
        assert artifact.authority_reference_ciphertext is not None
        assert artifact.notes_ciphertext is not None
        assert artifact.source_locator_hash is not None
        assert artifact.object_key is not None
        assert store.verify(artifact.object_key, artifact.sha256)
        assert len(custody) == 1
        assert custody[0].event_type == "CUSTODY_CREATED"
        assert custody[0].request_id == request_id
        assert len(audits) == 1
        assert audits[0].event_type == "EVIDENCE_INGESTED"
        assert audits[0].request_id == request_id
        assert job is not None
        assert job.state is JobState.PENDING
        assert job.idempotency_key == f"ingest:{evidence_id}:v1"
        assert job.queue == "ingest"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authorization_happens_before_any_evidence_byte_is_read(tmp_path: Path) -> None:
    service = preservation_service()
    _owner, case = await _seed_authorized_case()
    outsider = await _seed_outsider()
    stream = ReadTrackingStream(b"never read")

    async with async_session_factory() as session:
        with pytest.raises(CaseNotFound):
            await service.preserve_uploaded_evidence(
                session=session,
                actor=outsider,
                case_id=case.id,
                stream=stream,
                metadata=_metadata(),
                declared_media_type="text/plain",
                content_length="10",
                object_store=LocalObjectStore(tmp_path / "vault"),
                crypto=_crypto(),
                request_id=str(uuid4()),
            )
    assert stream.read_calls == 0
    assert await _artifact_count() == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_case_is_rejected_before_bytes_are_read(tmp_path: Path) -> None:
    service = preservation_service()
    actor, _case = await _seed_authorized_case()
    stream = ReadTrackingStream(b"never read")

    async with async_session_factory() as session:
        with pytest.raises(CaseNotFound):
            await service.preserve_uploaded_evidence(
                session=session,
                actor=actor,
                case_id=uuid4(),
                stream=stream,
                metadata=_metadata(),
                declared_media_type="text/plain",
                content_length="10",
                object_store=LocalObjectStore(tmp_path / "vault"),
                crypto=_crypto(),
                request_id=str(uuid4()),
            )
    assert stream.read_calls == 0
    assert await _artifact_count() == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oversize_stream_cleans_staging_and_creates_no_metadata(tmp_path: Path) -> None:
    service = preservation_service()
    actor, case = await _seed_authorized_case()
    store = LocalObjectStore(tmp_path / "vault")

    async with async_session_factory() as session:
        with pytest.raises(UploadSizeExceeded):
            await service.preserve_uploaded_evidence(
                session=session,
                actor=actor,
                case_id=case.id,
                stream=BytesIO(b"123456789"),
                metadata=_metadata(),
                declared_media_type="text/plain",
                content_length=None,
                object_store=store,
                crypto=_crypto(),
                limits=IngestionLimits(
                    max_upload_bytes=8,
                    sniff_bytes=4096,
                    stream_chunk_bytes=4096,
                ),
                request_id=str(uuid4()),
            )
        await session.rollback()

    assert await _artifact_count() == 0
    assert list((tmp_path / "vault" / ".staging").iterdir()) == []
    assert not (tmp_path / "vault" / "sha256").exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mime_mismatch_is_rejected_before_object_promotion(tmp_path: Path) -> None:
    service = preservation_service()
    actor, case = await _seed_authorized_case()
    store = LocalObjectStore(tmp_path / "vault")
    payload = b"%PDF-1.7\n"

    async with async_session_factory() as session:
        with pytest.raises(MediaTypeMismatch):
            await service.preserve_uploaded_evidence(
                session=session,
                actor=actor,
                case_id=case.id,
                stream=BytesIO(payload),
                metadata=_metadata(),
                declared_media_type="image/png",
                content_length=str(len(payload)),
                object_store=store,
                crypto=_crypto(),
                request_id=str(uuid4()),
            )
        await session.rollback()

    assert await _artifact_count() == 0
    assert list((tmp_path / "vault" / ".staging").iterdir()) == []
    assert not (tmp_path / "vault" / "sha256").exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_bytes_share_one_object_but_keep_separate_evidence_rows(
    tmp_path: Path,
) -> None:
    service = preservation_service()
    actor, case = await _seed_authorized_case()
    payload = b"same authorized synthetic bytes"
    store = LocalObjectStore(tmp_path / "vault")

    async with async_session_factory() as session:
        first = await service.preserve_uploaded_evidence(
            session=session,
            actor=actor,
            case_id=case.id,
            stream=BytesIO(payload),
            metadata=_metadata(),
            declared_media_type="text/plain",
            content_length=str(len(payload)),
            object_store=store,
            crypto=_crypto(),
            request_id=str(uuid4()),
        )
        second = await service.preserve_uploaded_evidence(
            session=session,
            actor=actor,
            case_id=case.id,
            stream=BytesIO(payload),
            metadata=_metadata(),
            declared_media_type="text/plain",
            content_length=str(len(payload)),
            object_store=store,
            crypto=_crypto(),
            request_id=str(uuid4()),
        )
        await session.commit()

    assert first.artifact.id != second.artifact.id
    assert first.artifact.object_key == second.artifact.object_key
    assert first.stored_object.created is True
    assert second.stored_object.created is False
    assert await _artifact_count() == 2
    object_files = [
        path for path in (tmp_path / "vault" / "sha256").rglob("*") if path.is_file()
    ]
    assert len(object_files) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_rollback_leaves_a_safe_unreferenced_content_object(
    tmp_path: Path,
) -> None:
    service = preservation_service()
    actor, case = await _seed_authorized_case()
    payload = b"safe orphan after simulated transaction rollback"
    store = LocalObjectStore(tmp_path / "vault")

    async with async_session_factory() as session:
        result = await service.preserve_uploaded_evidence(
            session=session,
            actor=actor,
            case_id=case.id,
            stream=BytesIO(payload),
            metadata=_metadata(),
            declared_media_type="text/plain",
            content_length=str(len(payload)),
            object_store=store,
            crypto=_crypto(),
            request_id=str(uuid4()),
        )
        object_key = result.stored_object.object_key
        digest = result.stored_object.sha256
        await session.rollback()

    assert await _artifact_count() == 0
    assert store.verify(object_key, digest) is True
