from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from darknetra_api.models.evidence import EvidenceSourceClass, EvidenceState
from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA512 = re.compile(r"^[0-9a-f]{128}$")
_OBJECT_KEY = re.compile(r"^sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$")


class EvidenceManifest(BaseModel):
    evidence_id: UUID
    media_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    sha256: str
    sha512: str | None = None
    object_key: str
    ingested_at: datetime

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256 must be lowercase hexadecimal")
        return value

    @field_validator("sha512")
    @classmethod
    def validate_sha512(cls, value: str | None) -> str | None:
        if value is not None and not _SHA512.fullmatch(value):
            raise ValueError("sha512 must be lowercase hexadecimal")
        return value

    @field_validator("object_key")
    @classmethod
    def validate_object_key(cls, value: str) -> str:
        if not _OBJECT_KEY.fullmatch(value):
            raise ValueError("object_key must use the content-addressed sha256 layout")
        return value


class EvidenceArtifactRead(BaseModel):
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
    created_at: datetime
    updated_at: datetime
