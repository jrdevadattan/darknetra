from __future__ import annotations

import base64
import secrets
from uuid import uuid4

import pytest
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.enums import JobStatus
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceSensitiveValue,
    EvidenceSensitiveValueKind,
    EvidenceSourceClass,
    EvidenceState,
)
from darknetra_api.models.job import AnalysisJob
from darknetra_api.policy.ingestion import (
    EvidenceSourceMetadata,
    EvidenceSourceType,
    PreservedUpload,
)
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.services.evidence_ingest import persist_preserved_upload
from darknetra_api.storage.base import StoredObject


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": secrets.token_bytes(32)},
        active_key_version="v1",
        blind_index_key=secrets.token_bytes(32),
    )


def preserved() -> PreservedUpload:
    digest = "a" * 64
    return PreservedUpload(
        stored=StoredObject(
            object_key=f"sha256/aa/aa/{digest}",
            sha256=digest,
            size_bytes=19,
        ),
        media_type="text/plain",
        parser_family="text",
    )


def metadata() -> EvidenceSourceMetadata:
    return EvidenceSourceMetadata.model_validate(
        {
            "source_class": EvidenceSourceClass.PUBLIC_OBSERVATION,
            "source_type": EvidenceSourceType.TEXT,
            "acquisition_method": "browser export",
            "captured_at": "2026-08-25T10:30:00Z",
            "source_locator": "https://example.test/item",
            "authority_reference": "policy-42",
            "protected_note": "restricted analyst note",
        }
    )


class FakeSession:
    def __init__(self, *, fail_on_type: type[object] | None = None) -> None:
        self.added: list[object] = []
        self.fail_on_type = fail_on_type
        self.committed = False
        self.rolled_back = False
        self.flush_snapshots: list[tuple[type[object], ...]] = []

    def add(self, value: object) -> None:
        if self.fail_on_type is not None and isinstance(value, self.fail_on_type):
            raise RuntimeError("injected persistence failure")
        self.added.append(value)

    def add_all(self, values: list[object]) -> None:
        for value in values:
            self.add(value)

    async def flush(self) -> None:
        self.flush_snapshots.append(tuple(type(value) for value in self.added))

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True
        self.added.clear()


@pytest.mark.asyncio
async def test_preservation_transaction_contains_redacted_events_values_and_pending_job() -> None:
    session = FakeSession()
    published: list[dict[str, str]] = []

    async def publisher(payload: dict[str, str]) -> None:
        assert session.committed is True
        published.append(payload)

    result = await persist_preserved_upload(
        session,  # type: ignore[arg-type]
        case_id=uuid4(),
        actor_user_id=uuid4(),
        metadata=metadata(),
        preserved=preserved(),
        crypto=crypto(),
        request_id="request-123",
        pipeline_version="v1",
        publisher=publisher,
    )

    artifact = next(value for value in session.added if isinstance(value, EvidenceArtifact))
    values = [value for value in session.added if isinstance(value, EvidenceSensitiveValue)]
    audit = next(value for value in session.added if isinstance(value, AuditEvent))
    custody = next(value for value in session.added if isinstance(value, CustodyEvent))
    job = next(value for value in session.added if isinstance(value, AnalysisJob))

    assert artifact.state is EvidenceState.PRESERVED
    assert artifact.object_key == preserved().stored.object_key
    assert {value.kind for value in values} == {
        EvidenceSensitiveValueKind.SOURCE_LOCATOR,
        EvidenceSensitiveValueKind.AUTHORITY_REFERENCE,
        EvidenceSensitiveValueKind.PROTECTED_NOTE,
    }
    assert [value.kind for value in values if value.blind_index] == [
        EvidenceSensitiveValueKind.SOURCE_LOCATOR
    ]
    assert audit.event_type == "EVIDENCE_INGESTED"
    assert custody.action == "CUSTODY_CREATED"
    assert job.status is JobStatus.PENDING
    assert job.idempotency_key == f"ingest:{artifact.id}:v1"
    assert session.flush_snapshots == [
        (EvidenceArtifact,),
        (EvidenceArtifact, EvidenceSensitiveValue, EvidenceSensitiveValue, EvidenceSensitiveValue),
        (
            EvidenceArtifact,
            EvidenceSensitiveValue,
            EvidenceSensitiveValue,
            EvidenceSensitiveValue,
            AuditEvent,
            CustodyEvent,
            AnalysisJob,
        ),
    ]
    assert published == [
        {
            "job_id": str(job.id),
            "case_id": str(artifact.case_id),
            "evidence_id": str(artifact.id),
            "pipeline_version": "v1",
        }
    ]
    serialized = repr(session.added) + repr(result)
    for secret in (
        "https://example.test/item",
        "policy-42",
        "restricted analyst note",
        preserved().stored.object_key,
        base64.b64encode(b"x" * 32).decode(),
    ):
        assert secret not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [EvidenceSensitiveValue, AuditEvent, CustodyEvent, AnalysisJob])
async def test_each_metadata_step_failure_rolls_back_without_touching_preserved_object(
    failure_type: type[object],
) -> None:
    session = FakeSession(fail_on_type=failure_type)
    published: list[dict[str, str]] = []

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        await persist_preserved_upload(
            session,  # type: ignore[arg-type]
            case_id=uuid4(),
            actor_user_id=uuid4(),
            metadata=metadata(),
            preserved=preserved(),
            crypto=crypto(),
            request_id="request-rollback",
            pipeline_version="v1",
            publisher=published.append,  # type: ignore[arg-type]
        )

    assert session.rolled_back is True
    assert session.committed is False
    assert session.added == []
    assert published == []


@pytest.mark.asyncio
async def test_publish_failure_leaves_committed_pending_job_retryable(caplog) -> None:
    session = FakeSession()

    async def unavailable_broker(payload: dict[str, str]) -> None:
        del payload
        raise RuntimeError("redis://user:secret@broker.internal unavailable")

    result = await persist_preserved_upload(
        session,  # type: ignore[arg-type]
        case_id=uuid4(),
        actor_user_id=uuid4(),
        metadata=metadata(),
        preserved=preserved(),
        crypto=crypto(),
        request_id="request-publish-failure",
        pipeline_version="v1",
        publisher=unavailable_broker,
    )

    job = next(value for value in session.added if isinstance(value, AnalysisJob))
    assert session.committed is True
    assert session.rolled_back is False
    assert job.status is JobStatus.PENDING
    assert result.dispatch_state == "PENDING_RETRY"
    assert "secret" not in repr(result)
    assert "ingest publish failed" in caplog.text
    assert "secret" not in caplog.text
