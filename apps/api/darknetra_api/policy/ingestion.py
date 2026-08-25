from __future__ import annotations

import csv
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import PurePath
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from darknetra_api.models.evidence import EvidenceSourceClass
from darknetra_api.storage.base import ObjectStore, StoredObject

MIB = 1024 * 1024
DEFAULT_UPLOAD_MAX_BYTES = 100 * MIB
HARD_UPLOAD_MAX_BYTES = 500 * MIB
DEFAULT_PREFIX_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 64 * 1024


class EvidenceSourceType(StrEnum):
    WARC = "WARC"
    WARC_GZ = "WARC_GZ"
    HTML = "HTML"
    XHTML = "XHTML"
    TEXT = "TEXT"
    JSON = "JSON"
    CSV = "CSV"
    ZIP = "ZIP"
    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WEBP"
    PDF = "PDF"


class EvidenceSourceMetadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        hide_input_in_errors=True,
    )

    source_class: EvidenceSourceClass
    source_type: EvidenceSourceType
    acquisition_method: str = Field(min_length=1, max_length=160)
    captured_at: datetime
    original_timezone: str | None = Field(default=None, min_length=1, max_length=80)
    tool_name: str | None = Field(default=None, min_length=1, max_length=120)
    tool_version: str | None = Field(default=None, min_length=1, max_length=80)
    source_locator: str | None = Field(
        default=None, min_length=1, max_length=8192, repr=False
    )
    authority_reference: str | None = Field(
        default=None, min_length=1, max_length=4096, repr=False
    )
    protected_note: str | None = Field(
        default=None, min_length=1, max_length=10000, repr=False
    )

    @field_validator("captured_at")
    @classmethod
    def captured_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include an explicit timezone")
        return value

    @model_validator(mode="after")
    def require_authority_reference(self) -> EvidenceSourceMetadata:
        governed = {
            EvidenceSourceClass.PUBLIC_OBSERVATION,
            EvidenceSourceClass.AUTHORIZED_IMPORT,
        }
        if self.source_class in governed and not self.authority_reference:
            raise ValueError("authority_reference is required for this source class")
        return self


class UploadPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DetectedUpload:
    source_type: EvidenceSourceType
    media_type: str
    parser_family: str


@dataclass(frozen=True, slots=True)
class PreservedUpload:
    stored: StoredObject = field(repr=False)
    media_type: str
    parser_family: str


_EXTENSION_TYPES = {
    ".warc": EvidenceSourceType.WARC,
    ".html": EvidenceSourceType.HTML,
    ".htm": EvidenceSourceType.HTML,
    ".xhtml": EvidenceSourceType.XHTML,
    ".txt": EvidenceSourceType.TEXT,
    ".json": EvidenceSourceType.JSON,
    ".csv": EvidenceSourceType.CSV,
    ".zip": EvidenceSourceType.ZIP,
    ".png": EvidenceSourceType.PNG,
    ".jpg": EvidenceSourceType.JPEG,
    ".jpeg": EvidenceSourceType.JPEG,
    ".webp": EvidenceSourceType.WEBP,
    ".pdf": EvidenceSourceType.PDF,
}

_DECLARED_MIME = {
    EvidenceSourceType.WARC: frozenset({"application/warc"}),
    EvidenceSourceType.WARC_GZ: frozenset(
        {"application/gzip", "application/x-gzip", "application/warc+gzip"}
    ),
    EvidenceSourceType.HTML: frozenset({"text/html"}),
    EvidenceSourceType.XHTML: frozenset({"application/xhtml+xml"}),
    EvidenceSourceType.TEXT: frozenset({"text/plain"}),
    EvidenceSourceType.JSON: frozenset({"application/json", "text/json"}),
    EvidenceSourceType.CSV: frozenset({"text/csv", "application/csv"}),
    EvidenceSourceType.ZIP: frozenset({"application/zip", "application/x-zip-compressed"}),
    EvidenceSourceType.PNG: frozenset({"image/png"}),
    EvidenceSourceType.JPEG: frozenset({"image/jpeg", "image/jpg"}),
    EvidenceSourceType.WEBP: frozenset({"image/webp"}),
    EvidenceSourceType.PDF: frozenset({"application/pdf"}),
}

_DETECTED = {
    EvidenceSourceType.WARC: ("application/warc", "warc"),
    EvidenceSourceType.WARC_GZ: ("application/warc+gzip", "warc"),
    EvidenceSourceType.HTML: ("text/html", "web"),
    EvidenceSourceType.XHTML: ("application/xhtml+xml", "web"),
    EvidenceSourceType.TEXT: ("text/plain", "text"),
    EvidenceSourceType.JSON: ("application/json", "json"),
    EvidenceSourceType.CSV: ("text/csv", "csv"),
    EvidenceSourceType.ZIP: ("application/zip", "archive"),
    EvidenceSourceType.PNG: ("image/png", "image"),
    EvidenceSourceType.JPEG: ("image/jpeg", "image"),
    EvidenceSourceType.WEBP: ("image/webp", "image"),
    EvidenceSourceType.PDF: ("application/pdf", "pdf"),
}


class _BoundedPrefixReplayStream:
    def __init__(
        self,
        source: BinaryIO,
        *,
        max_bytes: int,
        prefix_bytes: int,
    ) -> None:
        if not 1 <= max_bytes <= HARD_UPLOAD_MAX_BYTES:
            raise ValueError("max_bytes must be between 1 byte and the hard upload ceiling")
        if prefix_bytes < 1:
            raise ValueError("prefix_bytes must be positive")
        self._source = source
        self._max_bytes = max_bytes
        self._total_source_bytes = 0
        self._prefix = bytearray()
        self._replay_offset = 0
        self._source_eof = False
        while len(self._prefix) < prefix_bytes:
            requested = min(_READ_CHUNK_BYTES, prefix_bytes - len(self._prefix))
            chunk = self._read_source(requested)
            if chunk == b"":
                self._source_eof = True
                break
            self._prefix.extend(chunk)

    @property
    def prefix(self) -> bytes:
        return bytes(self._prefix)

    @property
    def prefix_is_complete(self) -> bool:
        return self._source_eof

    def read(self, size: int = -1) -> bytes:
        if size <= 0:
            raise ValueError("bounded upload reads require a positive size")
        output = bytearray()
        if self._replay_offset < len(self._prefix):
            replay_size = min(size, len(self._prefix) - self._replay_offset)
            output.extend(
                self._prefix[self._replay_offset : self._replay_offset + replay_size]
            )
            self._replay_offset += replay_size
        remaining = size - len(output)
        if remaining and not self._source_eof:
            chunk = self._read_source(remaining)
            if chunk == b"":
                self._source_eof = True
            else:
                output.extend(chunk)
        return bytes(output)

    def _read_source(self, requested: int) -> bytes:
        remaining_until_failure = self._max_bytes - self._total_source_bytes + 1
        if remaining_until_failure <= 0:
            raise UploadPolicyError("UPLOAD_TOO_LARGE", "upload exceeds the configured limit")
        chunk = self._source.read(min(requested, remaining_until_failure))
        if not isinstance(chunk, bytes):
            raise UploadPolicyError("INVALID_UPLOAD_STREAM", "upload stream must produce bytes")
        self._total_source_bytes += len(chunk)
        if self._total_source_bytes > self._max_bytes:
            raise UploadPolicyError("UPLOAD_TOO_LARGE", "upload exceeds the configured limit")
        return chunk


def _detected(source_type: EvidenceSourceType) -> DetectedUpload:
    media_type, parser_family = _DETECTED[source_type]
    return DetectedUpload(
        source_type=source_type,
        media_type=media_type,
        parser_family=parser_family,
    )


def _decoded_text(prefix: bytes) -> str | None:
    try:
        value = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if "\x00" in value:
        return None
    controls = sum(ord(character) < 32 and character not in "\t\r\n\f" for character in value)
    if controls > max(1, len(value) // 100):
        return None
    return value


def _looks_like_csv(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()][:8]
    if len(lines) < 2:
        return False
    sample = "\n".join(lines)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return False
    widths = [len(next(csv.reader([line], dialect=dialect))) for line in lines]
    return widths[0] > 1 and len(set(widths)) == 1


def detect_upload(prefix: bytes, *, complete: bool) -> DetectedUpload:
    if not prefix:
        raise UploadPolicyError("EMPTY_UPLOAD", "upload must contain at least one byte")
    if prefix.startswith((b"MZ", b"\x7fELF")) or prefix[:4] in {
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
    }:
        raise UploadPolicyError("UNSUPPORTED_MEDIA_TYPE", "executable uploads are not allowed")
    if prefix.startswith((b"WARC/1.0", b"WARC/1.1")):
        return _detected(EvidenceSourceType.WARC)
    if prefix.startswith(b"\x1f\x8b"):
        try:
            inflated = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(prefix, 32)
        except zlib.error as exc:
            raise UploadPolicyError("MALFORMED_MEDIA", "malformed gzip upload") from exc
        if inflated.startswith((b"WARC/1.0", b"WARC/1.1")):
            return _detected(EvidenceSourceType.WARC_GZ)
        if complete:
            raise UploadPolicyError("MALFORMED_MEDIA", "gzip upload is not a WARC")
        raise UploadPolicyError("UNSUPPORTED_MEDIA_TYPE", "gzip upload is not a WARC")
    if prefix.startswith(b"%PDF-"):
        return _detected(EvidenceSourceType.PDF)
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return _detected(EvidenceSourceType.PNG)
    if prefix.startswith(b"\xff\xd8\xff"):
        return _detected(EvidenceSourceType.JPEG)
    if len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
        return _detected(EvidenceSourceType.WEBP)
    if prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return _detected(EvidenceSourceType.ZIP)

    text = _decoded_text(prefix)
    if text is None:
        raise UploadPolicyError("UNSUPPORTED_MEDIA_TYPE", "binary upload type is not supported")
    stripped = text.lstrip()
    lowered = stripped[:4096].lower()
    if "http://www.w3.org/1999/xhtml" in lowered and "<html" in lowered:
        return _detected(EvidenceSourceType.XHTML)
    if re.match(r"(?is)^(?:<!doctype\s+html|<html(?:\s|>))", stripped):
        return _detected(EvidenceSourceType.HTML)
    if stripped.startswith(("{", "[")):
        if complete:
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise UploadPolicyError("MALFORMED_MEDIA", "malformed JSON upload") from exc
        return _detected(EvidenceSourceType.JSON)
    if _looks_like_csv(text):
        return _detected(EvidenceSourceType.CSV)
    if text:
        return _detected(EvidenceSourceType.TEXT)
    raise UploadPolicyError("EMPTY_UPLOAD", "upload must contain at least one byte")


def _filename_type(filename: str | None) -> EvidenceSourceType | None:
    if not filename:
        return None
    lowered = PurePath(filename).name.lower()
    if lowered.endswith(".warc.gz"):
        return EvidenceSourceType.WARC_GZ
    return _EXTENSION_TYPES.get(PurePath(lowered).suffix)


def validate_declared_upload(
    detected: DetectedUpload,
    *,
    metadata: EvidenceSourceMetadata,
    filename: str | None,
    declared_content_type: str | None,
) -> None:
    if metadata.source_type is not detected.source_type:
        raise UploadPolicyError(
            "SOURCE_TYPE_MISMATCH",
            "declared source type does not match the uploaded bytes",
        )
    extension_type = _filename_type(filename)
    if extension_type is not None and extension_type is not detected.source_type:
        raise UploadPolicyError(
            "FILENAME_TYPE_MISMATCH",
            "filename extension does not match the uploaded bytes",
        )
    declared = (declared_content_type or "").split(";", 1)[0].strip().lower()
    if declared and declared != "application/octet-stream" and declared not in _DECLARED_MIME[
        detected.source_type
    ]:
        raise UploadPolicyError(
            "DECLARED_MIME_MISMATCH",
            "declared MIME type does not match the uploaded bytes",
        )


def preserve_upload(
    *,
    stream: BinaryIO,
    object_store: ObjectStore,
    metadata: EvidenceSourceMetadata,
    filename: str | None,
    declared_content_type: str | None,
    max_bytes: int = DEFAULT_UPLOAD_MAX_BYTES,
    prefix_bytes: int = DEFAULT_PREFIX_BYTES,
) -> PreservedUpload:
    bounded = _BoundedPrefixReplayStream(
        stream,
        max_bytes=max_bytes,
        prefix_bytes=prefix_bytes,
    )
    detected = detect_upload(bounded.prefix, complete=bounded.prefix_is_complete)
    validate_declared_upload(
        detected,
        metadata=metadata,
        filename=filename,
        declared_content_type=declared_content_type,
    )
    stored = object_store.put_verified(bounded)
    if stored.size_bytes == 0:
        raise UploadPolicyError("EMPTY_UPLOAD", "upload must contain at least one byte")
    return PreservedUpload(
        stored=stored,
        media_type=detected.media_type,
        parser_family=detected.parser_family,
    )


__all__ = [
    "DEFAULT_PREFIX_BYTES",
    "DEFAULT_UPLOAD_MAX_BYTES",
    "HARD_UPLOAD_MAX_BYTES",
    "DetectedUpload",
    "EvidenceSourceMetadata",
    "EvidenceSourceType",
    "PreservedUpload",
    "UploadPolicyError",
    "detect_upload",
    "preserve_upload",
    "validate_declared_upload",
]
