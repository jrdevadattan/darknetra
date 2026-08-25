from __future__ import annotations

from datetime import datetime
from uuid import UUID

from darknetra_api.models.evidence import (
    EvidenceSensitiveValueKind,
    EvidenceSourceClass,
    EvidenceState,
)
from pydantic import BaseModel, ConfigDict, Field


class EvidenceArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    source_class: EvidenceSourceClass
    source_type: str
    acquisition_method: str
    collector_user_id: UUID
    captured_at: datetime
    ingested_at: datetime | None
    original_timezone: str | None
    media_type: str | None
    size_bytes: int | None
    sha256: str | None
    sha512: str | None
    state: EvidenceState
    quarantine_reason: str | None
    tool_name: str | None
    tool_version: str | None
    policy_restricted: bool
    allow_original_download: bool
    created_at: datetime
    updated_at: datetime


class EvidenceSensitiveValueSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    evidence_id: UUID
    kind: EvidenceSensitiveValueKind
    contact_kind: str | None
    wallet_network: str | None
    wallet_asset: str | None
    policy_sensitive: bool
    created_at: datetime


class EvidenceDerivationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    parent_evidence_id: UUID
    child_evidence_id: UUID
    transformation: str
    transformer_version: str
    parameters_json: dict[str, object]
    parameters_digest: str
    created_at: datetime


class CustodyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    evidence_id: UUID
    actor_user_id: UUID | None
    action: str
    request_id: str
    integrity_sha256: str | None
    metadata_json: dict[str, object]
    created_at: datetime


class SensitiveValueRevealRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class SensitiveValueRevealResponse(BaseModel):
    value: str


__all__ = [
    "CustodyEventResponse",
    "EvidenceArtifactResponse",
    "EvidenceDerivationResponse",
    "EvidenceSensitiveValueSummary",
    "SensitiveValueRevealRequest",
    "SensitiveValueRevealResponse",
]
