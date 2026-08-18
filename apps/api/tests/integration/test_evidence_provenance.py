from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.enums import CaseSensitivity
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceDerivation,
    EvidenceSourceClass,
    EvidenceState,
)
from darknetra_api.models.job import Job
from darknetra_api.models.user import User
from darknetra_api.schemas.evidence import EvidenceArtifactRead, EvidenceManifest
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.services.evidence import (
    EvidenceDigestImmutableError,
    preserve_evidence_manifest,
)
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, StatementError

SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA512_A = "c" * 128


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


async def _seed_case() -> tuple[User, Case]:
    async with async_session_factory() as session:
        username = f"evidence-owner-{uuid4().hex[:10]}"
        owner = User(
            username=username,
            username_normalized=username.casefold(),
            display_name="Synthetic Evidence Owner",
            password_hash="unused",
            global_roles=[],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code=f"EVD-{uuid4().hex[:10].upper()}",
            title="Synthetic evidence provenance case",
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Authorized synthetic schema test",
        )
        session.add(case)
        await session.commit()
        await session.refresh(owner)
        await session.refresh(case)
        return owner, case


def _artifact(*, case_id: UUID, collector_user_id: UUID, evidence_id: UUID | None = None) -> EvidenceArtifact:
    return EvidenceArtifact(
        id=evidence_id or uuid4(),
        case_id=case_id,
        source_class=EvidenceSourceClass.SYNTHETIC,
        source_type="synthetic.fixture",
        acquisition_method="authorized_test_generation",
        collector_user_id=collector_user_id,
        captured_at=datetime.now(UTC),
        original_timezone="UTC",
        state=EvidenceState.STAGING,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_evidence_id_is_unique_and_case_foreign_key_is_enforced() -> None:
    owner, case = await _seed_case()
    duplicate_id = uuid4()

    async with async_session_factory() as session:
        session.add_all(
            [
                _artifact(case_id=case.id, collector_user_id=owner.id, evidence_id=duplicate_id),
                _artifact(case_id=case.id, collector_user_id=owner.id, evidence_id=duplicate_id),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with async_session_factory() as session:
        session.add(_artifact(case_id=uuid4(), collector_user_id=owner.id))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_source_class_and_state_are_database_enforced() -> None:
    owner, case = await _seed_case()
    async with async_session_factory() as session:
        invalid = _artifact(case_id=case.id, collector_user_id=owner.id)
        invalid.source_class = "UNAPPROVED_SOURCE"  # type: ignore[assignment]
        invalid.state = "NOT_A_STATE"  # type: ignore[assignment]
        session.add(invalid)
        with pytest.raises((IntegrityError, StatementError)):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_manifest_is_set_once_and_expected_digests_cannot_be_rewritten() -> None:
    owner, case = await _seed_case()
    evidence_id = uuid4()
    async with async_session_factory() as session:
        session.add(_artifact(case_id=case.id, collector_user_id=owner.id, evidence_id=evidence_id))
        await session.commit()

    async with async_session_factory() as session:
        artifact = await session.get(EvidenceArtifact, evidence_id)
        assert artifact is not None
        preserve_evidence_manifest(
            artifact,
            media_type="text/plain",
            size_bytes=17,
            sha256=SHA256_A,
            sha512=SHA512_A,
            object_key=f"sha256/aa/aa/{SHA256_A}",
            ingested_at=datetime.now(UTC),
        )
        await session.commit()

    async with async_session_factory() as session:
        artifact = await session.get(EvidenceArtifact, evidence_id)
        assert artifact is not None
        assert artifact.state is EvidenceState.PRESERVED
        assert artifact.sha256 == SHA256_A
        assert artifact.sha512 == SHA512_A
        assert artifact.size_bytes == 17

        with pytest.raises(EvidenceDigestImmutableError):
            preserve_evidence_manifest(
                artifact,
                media_type="text/plain",
                size_bytes=18,
                sha256=SHA256_B,
                sha512=None,
                object_key=f"sha256/bb/bb/{SHA256_B}",
            )

        artifact.sha256 = SHA256_B
        with pytest.raises(EvidenceDigestImmutableError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_derivation_records_parent_child_lineage_and_rejects_self_reference() -> None:
    owner, case = await _seed_case()
    parent = _artifact(case_id=case.id, collector_user_id=owner.id)
    child = _artifact(case_id=case.id, collector_user_id=owner.id)

    async with async_session_factory() as session:
        session.add_all([parent, child])
        await session.flush()
        derivation = EvidenceDerivation(
            parent_evidence_id=parent.id,
            child_evidence_id=child.id,
            transformation="normalized_text",
            transformer_version="1.0.0",
            parameters_json={"encoding": "utf-8", "active_content": "removed"},
        )
        session.add(derivation)
        await session.commit()
        await session.refresh(derivation)
        assert derivation.parent_evidence_id == parent.id
        assert derivation.child_evidence_id == child.id
        assert derivation.parameters_json["active_content"] == "removed"

    async with async_session_factory() as session:
        session.add(
            EvidenceDerivation(
                parent_evidence_id=parent.id,
                child_evidence_id=parent.id,
                transformation="invalid_self_reference",
                transformer_version="1.0.0",
                parameters_json={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_custody_events_are_append_only() -> None:
    owner, case = await _seed_case()
    artifact = _artifact(case_id=case.id, collector_user_id=owner.id)
    event_id = uuid4()

    async with async_session_factory() as session:
        session.add(artifact)
        await session.flush()
        session.add(
            CustodyEvent(
                id=event_id,
                evidence_id=artifact.id,
                case_id=case.id,
                actor_user_id=owner.id,
                event_type="CUSTODY_CREATED",
                request_id=str(uuid4()),
                reason="Initial synthetic custody record",
                metadata_json={"source": "test"},
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        event = await session.get(CustodyEvent, event_id)
        assert event is not None
        event.reason = "Attempted rewrite"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()

    async with async_session_factory() as session:
        event = await session.get(CustodyEvent, event_id)
        assert event is not None
        await session.delete(event)
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_encrypted_metadata_round_trips_without_automatic_plaintext_exposure() -> None:
    owner, case = await _seed_case()
    crypto = SensitiveFieldCrypto(
        field_keys={"v1": b"1" * 32},
        active_key_version="v1",
        blind_index_key=b"2" * 32,
    )
    artifact = _artifact(case_id=case.id, collector_user_id=owner.id)
    artifact.source_locator_ciphertext = crypto.encrypt(
        "http://example.invalid/authorized-observation",
        purpose="evidence.source_locator",
        resource_id=str(artifact.id),
    )
    artifact.source_locator_hash = crypto.blind_index(
        "http://example.invalid/authorized-observation",
        purpose="evidence.source_locator",
    )
    artifact.authority_reference_ciphertext = crypto.encrypt(
        "AUTH-REFERENCE-001",
        purpose="evidence.authority_reference",
        resource_id=str(artifact.id),
    )
    artifact.notes_ciphertext = crypto.encrypt(
        "Restricted synthetic test note",
        purpose="evidence.notes",
        resource_id=str(artifact.id),
    )

    async with async_session_factory() as session:
        session.add(artifact)
        await session.commit()
        evidence_id = artifact.id

    async with async_session_factory() as session:
        stored = await session.get(EvidenceArtifact, evidence_id)
        assert stored is not None
        assert stored.source_locator_ciphertext is not None
        assert (
            crypto.decrypt(
                stored.source_locator_ciphertext,
                purpose="evidence.source_locator",
                resource_id=str(stored.id),
            )
            == "http://example.invalid/authorized-observation"
        )
        safe = EvidenceArtifactRead.model_validate(stored)
        dumped = safe.model_dump()
        assert "source_locator_ciphertext" not in dumped
        assert "authority_reference_ciphertext" not in dumped
        assert "notes_ciphertext" not in dumped
        assert "object_key" not in dumped


def test_manifest_schema_validates_digest_and_size_contract() -> None:
    manifest = EvidenceManifest(
        evidence_id=uuid4(),
        media_type="text/plain",
        size_bytes=17,
        sha256=SHA256_A,
        sha512=SHA512_A,
        object_key=f"sha256/aa/aa/{SHA256_A}",
        ingested_at=datetime.now(UTC),
    )
    assert manifest.sha256 == SHA256_A

    with pytest.raises(ValidationError):
        EvidenceManifest(
            evidence_id=uuid4(),
            media_type="text/plain",
            size_bytes=-1,
            sha256="not-a-digest",
            object_key="unsafe/path",
            ingested_at=datetime.now(UTC),
        )
