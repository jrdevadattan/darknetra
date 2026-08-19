from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator

from darknetra_api.models.evidence import EvidenceSourceClass

_MIB = 1024 * 1024
_DEFAULT_MAX_UPLOAD_BYTES = 100 * _MIB
_ABSOLUTE_HARD_CEILING_BYTES = 500 * _MIB
_MEDIA_TYPE_TOKEN = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_CONTROL_BYTES = frozenset(range(9)) | frozenset(range(11, 13)) | frozenset(range(14, 32))
_EXECUTABLE_PREFIXES = (b"\x7fELF", b"MZ", b"#!")


class IngestionPolicyError(ValueError):
    """Base class for fail-closed ingestion-policy failures."""


class UploadSizeExceeded(IngestionPolicyError):
    """The declared or observed upload exceeds the active policy."""


class InvalidContentLength(IngestionPolicyError):
    """A declared content length is malformed or negative."""


class UnsupportedMediaType(IngestionPolicyError):
    """Bytes do not match an approved evidence parser family."""


class MediaTypeMismatch(IngestionPolicyError):
    """A concrete caller declaration contradicts byte-level detection."""


@dataclass(frozen=True, slots=True)
class IngestionLimits:
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES
    hard_ceiling_bytes: int = _ABSOLUTE_HARD_CEILING_BYTES
    sniff_bytes: int = 64 * 1024
    stream_chunk_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_upload_bytes <= 0 or self.hard_ceiling_bytes <= 0:
            raise ValueError("upload limits must be positive")
        if self.hard_ceiling_bytes > _ABSOLUTE_HARD_CEILING_BYTES:
            raise ValueError("configured hard ceiling exceeds the absolute hard ceiling")
        if self.max_upload_bytes > self.hard_ceiling_bytes:
            raise ValueError("max upload size exceeds the hard ceiling")
        if not 4096 <= self.sniff_bytes <= 1024 * 1024:
            raise ValueError("sniff byte limit must be between 4096 and 1048576")
        if not 4096 <= self.stream_chunk_bytes <= 8 * 1024 * 1024:
            raise ValueError("stream chunk size is outside the supported range")


NonEmptyShort = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]


class EvidenceSourceMetadata(BaseModel):
    model_config = {"extra": "forbid"}

    source_class: EvidenceSourceClass
    source_type: NonEmptyShort
    acquisition_method: NonEmptyShort
    captured_at: datetime
    original_timezone: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ]
    authority_reference: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ] = None
    source_locator: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    ] = None
    notes: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    ] = None
    tool_name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ] = None
    tool_version: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ] = None

    @model_validator(mode="after")
    def validate_governance_and_time(self) -> EvidenceSourceMetadata:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.source_class in {
            EvidenceSourceClass.PUBLIC_OBSERVATION,
            EvidenceSourceClass.AUTHORIZED_IMPORT,
        } and not self.authority_reference:
            raise ValueError(
                "authority_reference is required for PUBLIC_OBSERVATION "
                "and AUTHORIZED_IMPORT"
            )
        return self


@dataclass(frozen=True, slots=True)
class DetectedMedia:
    media_type: str
    parser_family: str


_ALIASES = {
    "application/x-gzip": "application/gzip",
    "application/x-zip-compressed": "application/zip",
    "image/jpg": "image/jpeg",
    "application/xhtml+xml": "text/html",
    "application/warc+gzip": "application/gzip",
}


def normalize_media_type(value: str | None) -> str | None:
    if value is None:
        return None
    token = value.split(";", 1)[0].strip().lower()
    token = _ALIASES.get(token, token)
    if not token or not _MEDIA_TYPE_TOKEN.fullmatch(token):
        raise UnsupportedMediaType("declared media type is malformed")
    return token


def validate_content_length(
    value: str | int | None,
    *,
    limits: IngestionLimits,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InvalidContentLength("Content-Length must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidContentLength("Content-Length must be a non-negative integer") from exc
    if parsed < 0:
        raise InvalidContentLength("Content-Length must be a non-negative integer")
    if parsed > limits.max_upload_bytes:
        raise UploadSizeExceeded(
            f"declared upload size exceeds {limits.max_upload_bytes} bytes"
        )
    return parsed


def _looks_like_text(data: bytes) -> bool:
    if not data or b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    control_count = sum(byte in _CONTROL_BYTES for byte in data)
    return control_count / len(data) <= 0.01


def _require_declared_match(declared: str | None, detected: str) -> None:
    if declared in {None, "application/octet-stream"}:
        return
    if declared == detected:
        return
    raise MediaTypeMismatch(
        f"declared media type {declared!r} does not match detected {detected!r}"
    )


def detect_media_type(
    data: bytes,
    *,
    declared_media_type: str | None = None,
) -> DetectedMedia:
    if not isinstance(data, bytes):
        raise TypeError("sniff data must be bytes")
    if not data:
        raise UnsupportedMediaType("empty evidence is not supported")
    if data.startswith(_EXECUTABLE_PREFIXES):
        raise UnsupportedMediaType("executable content is not an approved evidence type")

    declared = normalize_media_type(declared_media_type)
    stripped = data.lstrip()
    lower = stripped[:4096].lower()

    if data.startswith(b"%PDF-"):
        detected = DetectedMedia("application/pdf", "pdf")
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = DetectedMedia("image/png", "image")
    elif data.startswith(b"\xff\xd8\xff"):
        detected = DetectedMedia("image/jpeg", "image")
    elif len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        detected = DetectedMedia("image/webp", "image")
    elif data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        detected = DetectedMedia("application/zip", "archive")
    elif data.startswith((b"WARC/1.0", b"WARC/1.1")):
        detected = DetectedMedia("application/warc", "warc")
    elif data.startswith(b"\x1f\x8b"):
        detected = DetectedMedia("application/gzip", "warc_gzip_candidate")
    elif lower.startswith((b"<!doctype html", b"<html")) or b"<html" in lower:
        detected = DetectedMedia("text/html", "html")
    elif _looks_like_text(data):
        text = data.decode("utf-8")
        if stripped.startswith((b"{", b"[")):
            try:
                json.loads(text)
            except json.JSONDecodeError:
                detected = DetectedMedia("text/plain", "text")
            else:
                detected = DetectedMedia("application/json", "json")
        elif declared == "text/csv":
            detected = DetectedMedia("text/csv", "csv")
        else:
            detected = DetectedMedia("text/plain", "text")
    else:
        raise UnsupportedMediaType("bytes do not match an approved evidence parser family")

    _require_declared_match(declared, detected.media_type)
    return detected
