from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.enums import JobStatus
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceSensitiveValueKind,
    EvidenceState,
)
from darknetra_api.models.job import AnalysisJob
from darknetra_api.policy.ingestion import EvidenceSourceMetadata, PreservedUpload
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.services.evidence import build_sensitive_value, preserve_evidence_manifest

INGEST_TASK_NAME = "darknetra.ingest.process_evidence"
DEFAULT_PIPELINE_VERSION = "v1"
_PIPELINE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
logger = logging.getLogger(__name__)

IngestPayload = dict[str, str]
IngestPublisher = Callable[[IngestPayload], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class IngestResult:
    evidence_id: UUID
    case_id: UUID
    job_id: UUID
    media_type: str
    size_bytes: int
    sha256: str
    evidence_state: EvidenceState
    job_status: JobStatus
    dispatch_state: Literal["PUBLISHED", "PENDING_RETRY"]


def ingest_payload(
    *,
    job_id: UUID,
    case_id: UUID,
    evidence_id: UUID,
    pipeline_version: str,
) -> IngestPayload:
    return {
        "job_id": str(job_id),
        "case_id": str(case_id),
        "evidence_id": str(evidence_id),
        "pipeline_version": pipeline_version,
    }


async def _publish(publisher: IngestPublisher, payload: IngestPayload) -> None:
    result = publisher(payload)
    if inspect.isawaitable(result):
        await result


def publish_ingest_payload(payload: IngestPayload) -> None:
    """Publish only identifiers through Celery's JSON serializer."""

    from darknetra_api.jobs.celery_app import celery_app

    celery_app.send_task(
        INGEST_TASK_NAME,
        kwargs=payload,
        task_id=payload["job_id"],
        queue="ingest",
    )


async def persist_preserved_upload(
    session: AsyncSession,
    *,
    case_id: UUID,
    actor_user_id: UUID,
    metadata: EvidenceSourceMetadata,
    preserved: PreservedUpload,
    crypto: SensitiveFieldCrypto,
    request_id: str,
    pipeline_version: str = DEFAULT_PIPELINE_VERSION,
    publisher: IngestPublisher = publish_ingest_payload,
) -> IngestResult:
    """Commit authoritative ingestion state once, then attempt broker delivery."""

    if _PIPELINE_VERSION_PATTERN.fullmatch(pipeline_version) is None:
        raise ValueError("pipeline_version must use the public version grammar")
    evidence_id = uuid4()
    artifact = EvidenceArtifact(
        id=evidence_id,
        case_id=case_id,
        source_class=metadata.source_class,
        source_type=metadata.source_type.value,
        acquisition_method=metadata.acquisition_method,
        collector_user_id=actor_user_id,
        captured_at=metadata.captured_at,
        original_timezone=metadata.original_timezone,
        tool_name=metadata.tool_name,
        tool_version=metadata.tool_version,
        state=EvidenceState.STAGING,
    )
    preserve_evidence_manifest(
        artifact,
        media_type=preserved.media_type,
        size_bytes=preserved.stored.size_bytes,
        sha256=preserved.stored.sha256,
        object_key=preserved.stored.object_key,
    )

    protected_values = []
    for kind, plaintext in (
        (EvidenceSensitiveValueKind.SOURCE_LOCATOR, metadata.source_locator),
        (EvidenceSensitiveValueKind.AUTHORITY_REFERENCE, metadata.authority_reference),
        (EvidenceSensitiveValueKind.PROTECTED_NOTE, metadata.protected_note),
    ):
        if plaintext is not None:
            protected_values.append(
                build_sensitive_value(
                    case_id=case_id,
                    evidence_id=evidence_id,
                    kind=kind,
                    plaintext=plaintext,
                    crypto=crypto,
                )
            )

    audit = AuditEvent(
        actor_user_id=actor_user_id,
        event_type="EVIDENCE_INGESTED",
        resource_type="evidence",
        resource_id=str(evidence_id),
        case_id=case_id,
        request_id=request_id,
        metadata_json={
            "source_class": metadata.source_class.value,
            "source_type": metadata.source_type.value,
            "media_type": preserved.media_type,
            "size_bytes": preserved.stored.size_bytes,
            "sha256": preserved.stored.sha256,
        },
    )
    custody = CustodyEvent(
        case_id=case_id,
        evidence_id=evidence_id,
        actor_user_id=actor_user_id,
        action="CUSTODY_CREATED",
        request_id=request_id,
        integrity_sha256=preserved.stored.sha256,
        metadata_json={
            "source_class": metadata.source_class.value,
            "source_type": metadata.source_type.value,
            "media_type": preserved.media_type,
        },
    )
    job_id = uuid4()
    job = AnalysisJob(
        id=job_id,
        case_id=case_id,
        resource_type="evidence",
        resource_id=evidence_id,
        task_name=INGEST_TASK_NAME,
        queue="ingest",
        idempotency_key=f"ingest:{evidence_id}:{pipeline_version}",
        status=JobStatus.PENDING,
    )
    try:
        session.add(artifact)
        await session.flush()
        session.add_all(protected_values)
        await session.flush()
        session.add(audit)
        session.add(custody)
        session.add(job)
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    payload = ingest_payload(
        job_id=job_id,
        case_id=case_id,
        evidence_id=evidence_id,
        pipeline_version=pipeline_version,
    )
    dispatch_state: Literal["PUBLISHED", "PENDING_RETRY"] = "PUBLISHED"
    try:
        await _publish(publisher, payload)
    except Exception:  # noqa: BLE001
        # Broker clients raise multiple transport-specific exception families.
        logger.warning(
            "ingest publish failed job_id=%s evidence_id=%s",
            job_id,
            evidence_id,
        )
        dispatch_state = "PENDING_RETRY"

    return IngestResult(
        evidence_id=evidence_id,
        case_id=case_id,
        job_id=job_id,
        media_type=preserved.media_type,
        size_bytes=preserved.stored.size_bytes,
        sha256=preserved.stored.sha256,
        evidence_state=artifact.state,
        job_status=job.status,
        dispatch_state=dispatch_state,
    )


__all__ = [
    "DEFAULT_PIPELINE_VERSION",
    "INGEST_TASK_NAME",
    "IngestPayload",
    "IngestPublisher",
    "IngestResult",
    "ingest_payload",
    "persist_preserved_upload",
    "publish_ingest_payload",
]
