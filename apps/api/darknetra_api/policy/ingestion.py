from __future__ import annotations

import codecs
import csv
import json
import re
import zlib
from collections.abc import Callable
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
_MAX_JSON_NESTING = 256


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
    source_locator: str | None = Field(default=None, min_length=1, max_length=8192, repr=False)
    authority_reference: str | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    protected_note: str | None = Field(default=None, min_length=1, max_length=10000, repr=False)

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
            output.extend(self._prefix[self._replay_offset : self._replay_offset + replay_size])
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


class _StreamingJsonValidator:
    """Validate JSON syntax incrementally with constant token memory."""

    def __init__(self) -> None:
        self._root_state = "value"
        self._stack: list[list[str]] = []
        self._mode = "normal"
        self._string_is_key = False
        self._unicode_remaining = 0
        self._literal_remaining = ""
        self._number_state = ""

    def feed(self, text: str) -> None:
        offset = 0
        while offset < len(text):
            character = text[offset]
            consumed = self._feed_character(character)
            if consumed:
                offset += 1

    def finish(self) -> None:
        if self._mode == "number":
            if self._number_state not in {"zero", "integer", "fraction", "exponent"}:
                self._malformed()
            self._mode = "normal"
            self._complete_value()
        if self._mode != "normal" or self._stack or self._root_state != "end":
            self._malformed()

    def _feed_character(self, character: str) -> bool:
        if self._mode == "string":
            if character == '"':
                self._mode = "normal"
                if self._string_is_key:
                    self._stack[-1][1] = "colon"
                else:
                    self._complete_value()
            elif character == "\\":
                self._mode = "string_escape"
            elif ord(character) < 0x20:
                self._malformed()
            return True

        if self._mode == "string_escape":
            if character == "u":
                self._mode = "string_unicode"
                self._unicode_remaining = 4
            elif character in '"\\/bfnrt':
                self._mode = "string"
            else:
                self._malformed()
            return True

        if self._mode == "string_unicode":
            if character not in "0123456789abcdefABCDEF":
                self._malformed()
            self._unicode_remaining -= 1
            if self._unicode_remaining == 0:
                self._mode = "string"
            return True

        if self._mode == "literal":
            if not self._literal_remaining or character != self._literal_remaining[0]:
                self._malformed()
            self._literal_remaining = self._literal_remaining[1:]
            if not self._literal_remaining:
                self._mode = "normal"
                self._complete_value()
            return True

        if self._mode == "number":
            return self._feed_number_character(character)

        if character in " \t\r\n":
            return True
        if self._root_state == "end" and not self._stack:
            self._malformed()
        if character == "{":
            self._require_value_position()
            self._push("object", "key_or_end")
            return True
        if character == "[":
            self._require_value_position()
            self._push("array", "value_or_end")
            return True
        if character == '"':
            if self._expects_object_key():
                self._string_is_key = True
            else:
                self._require_value_position()
                self._string_is_key = False
            self._mode = "string"
            return True
        if character == "}":
            self._close("object", {"key_or_end", "comma_or_end"})
            return True
        if character == "]":
            self._close("array", {"value_or_end", "comma_or_end"})
            return True
        if character == ":":
            if not self._stack or self._stack[-1] != ["object", "colon"]:
                self._malformed()
            self._stack[-1][1] = "value"
            return True
        if character == ",":
            if not self._stack or self._stack[-1][1] != "comma_or_end":
                self._malformed()
            self._stack[-1][1] = "key" if self._stack[-1][0] == "object" else "value"
            return True
        if character in "tfn":
            self._require_value_position()
            self._mode = "literal"
            self._literal_remaining = {
                "t": "rue",
                "f": "alse",
                "n": "ull",
            }[character]
            return True
        if character == "-" or character in "0123456789":
            self._require_value_position()
            self._mode = "number"
            if character == "-":
                self._number_state = "minus"
            elif character == "0":
                self._number_state = "zero"
            else:
                self._number_state = "integer"
            return True
        self._malformed()

    def _feed_number_character(self, character: str) -> bool:
        state = self._number_state
        if state == "minus":
            if character == "0":
                self._number_state = "zero"
            elif character in "123456789":
                self._number_state = "integer"
            else:
                self._malformed()
            return True
        if state == "zero":
            if character == ".":
                self._number_state = "fraction_start"
                return True
            if character in "eE":
                self._number_state = "exponent_start"
                return True
            return self._finish_number_and_reprocess()
        if state == "integer":
            if character in "0123456789":
                return True
            if character == ".":
                self._number_state = "fraction_start"
                return True
            if character in "eE":
                self._number_state = "exponent_start"
                return True
            return self._finish_number_and_reprocess()
        if state == "fraction_start":
            if character not in "0123456789":
                self._malformed()
            self._number_state = "fraction"
            return True
        if state == "fraction":
            if character in "0123456789":
                return True
            if character in "eE":
                self._number_state = "exponent_start"
                return True
            return self._finish_number_and_reprocess()
        if state == "exponent_start":
            if character in "+-":
                self._number_state = "exponent_sign"
            elif character in "0123456789":
                self._number_state = "exponent"
            else:
                self._malformed()
            return True
        if state == "exponent_sign":
            if character not in "0123456789":
                self._malformed()
            self._number_state = "exponent"
            return True
        if state == "exponent":
            if character in "0123456789":
                return True
            return self._finish_number_and_reprocess()
        self._malformed()

    def _finish_number_and_reprocess(self) -> bool:
        self._mode = "normal"
        self._complete_value()
        return False

    def _expects_object_key(self) -> bool:
        return bool(
            self._stack
            and self._stack[-1][0] == "object"
            and self._stack[-1][1] in {"key_or_end", "key"}
        )

    def _require_value_position(self) -> None:
        if not self._stack:
            if self._root_state != "value":
                self._malformed()
            return
        kind, state = self._stack[-1]
        if kind == "array" and state in {"value_or_end", "value"}:
            return
        if kind == "object" and state == "value":
            return
        self._malformed()

    def _push(self, kind: str, state: str) -> None:
        if len(self._stack) >= _MAX_JSON_NESTING:
            self._malformed()
        self._stack.append([kind, state])

    def _close(self, kind: str, allowed_states: set[str]) -> None:
        if (
            not self._stack
            or self._stack[-1][0] != kind
            or self._stack[-1][1] not in allowed_states
        ):
            self._malformed()
        self._stack.pop()
        self._complete_value()

    def _complete_value(self) -> None:
        if not self._stack:
            if self._root_state != "value":
                self._malformed()
            self._root_state = "end"
            return
        kind, state = self._stack[-1]
        if kind == "array" and state in {"value_or_end", "value"}:
            self._stack[-1][1] = "comma_or_end"
            return
        if kind == "object" and state == "value":
            self._stack[-1][1] = "comma_or_end"
            return
        self._malformed()

    @staticmethod
    def _malformed() -> None:
        raise UploadPolicyError("MALFORMED_MEDIA", "malformed JSON upload")


class _StreamingTextValidator:
    def __init__(self, *, validate_json: bool) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
        self._characters = 0
        self._disallowed_controls = 0
        self._json = _StreamingJsonValidator() if validate_json else None

    def feed(self, chunk: bytes) -> None:
        try:
            text = self._decoder.decode(chunk, final=False)
        except UnicodeDecodeError as exc:
            raise UploadPolicyError(
                "UNSUPPORTED_MEDIA_TYPE",
                "text upload is not valid UTF-8",
            ) from exc
        self._observe(text)

    def finish(self) -> None:
        try:
            text = self._decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise UploadPolicyError(
                "UNSUPPORTED_MEDIA_TYPE",
                "text upload is not valid UTF-8",
            ) from exc
        self._observe(text)
        if self._disallowed_controls > max(1, self._characters // 100):
            raise UploadPolicyError(
                "UNSUPPORTED_MEDIA_TYPE",
                "text upload contains binary control bytes",
            )
        if self._json is not None:
            self._json.finish()

    def _observe(self, text: str) -> None:
        if "\x00" in text:
            raise UploadPolicyError(
                "UNSUPPORTED_MEDIA_TYPE",
                "text upload contains a NUL byte",
            )
        self._characters += len(text)
        self._disallowed_controls += sum(
            ord(character) < 32 and character not in "\t\r\n\f" for character in text
        )
        if self._json is not None:
            self._json.feed(text)


class _ValidatedUploadStream:
    def __init__(self, source: _BoundedPrefixReplayStream, detected: DetectedUpload) -> None:
        self._source = source
        self._validator = (
            _StreamingTextValidator(validate_json=detected.source_type is EvidenceSourceType.JSON)
            if detected.source_type
            in {
                EvidenceSourceType.HTML,
                EvidenceSourceType.XHTML,
                EvidenceSourceType.TEXT,
                EvidenceSourceType.JSON,
                EvidenceSourceType.CSV,
            }
            else None
        )
        self.finished = False

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        if chunk:
            if self._validator is not None:
                self._validator.feed(chunk)
            return chunk
        if not self.finished:
            if self._validator is not None:
                self._validator.finish()
            self.finished = True
        return b""


class _DeferredDeclarationStream:
    """Withhold object-store EOF until the whole multipart envelope is valid."""

    def __init__(
        self,
        source: _ValidatedUploadStream,
        *,
        detected: DetectedUpload,
        metadata_provider: Callable[[], EvidenceSourceMetadata],
        filename: str | None,
        declared_content_type: str | None,
    ) -> None:
        self._source = source
        self._detected = detected
        self._metadata_provider = metadata_provider
        self._filename = filename
        self._declared_content_type = declared_content_type
        self.metadata: EvidenceSourceMetadata | None = None

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        if chunk:
            return chunk
        if self.metadata is None:
            metadata = self._metadata_provider()
            validate_declared_upload(
                self._detected,
                metadata=metadata,
                filename=self._filename,
                declared_content_type=self._declared_content_type,
            )
            self.metadata = metadata
        return b""


def _detected(source_type: EvidenceSourceType) -> DetectedUpload:
    media_type, parser_family = _DETECTED[source_type]
    return DetectedUpload(
        source_type=source_type,
        media_type=media_type,
        parser_family=parser_family,
    )


def _decoded_text(prefix: bytes, *, complete: bool) -> str | None:
    try:
        decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
        value = decoder.decode(prefix, final=complete)
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

    text = _decoded_text(prefix, complete=complete)
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
    if (
        declared
        and declared != "application/octet-stream"
        and declared not in _DECLARED_MIME[detected.source_type]
    ):
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
    validated = _ValidatedUploadStream(bounded, detected)
    stored = object_store.put_verified(validated)
    if not validated.finished:
        raise UploadPolicyError(
            "INVALID_UPLOAD_STREAM",
            "object store did not consume the complete upload stream",
        )
    if stored.size_bytes == 0:
        raise UploadPolicyError("EMPTY_UPLOAD", "upload must contain at least one byte")
    return PreservedUpload(
        stored=stored,
        media_type=detected.media_type,
        parser_family=detected.parser_family,
    )


def preserve_upload_after_envelope(
    *,
    stream: BinaryIO,
    object_store: ObjectStore,
    metadata_provider: Callable[[], EvidenceSourceMetadata],
    filename: str | None,
    declared_content_type: str | None,
    max_bytes: int = DEFAULT_UPLOAD_MAX_BYTES,
    prefix_bytes: int = DEFAULT_PREFIX_BYTES,
) -> tuple[EvidenceSourceMetadata, PreservedUpload]:
    """Preserve a stream only after its multipart envelope is declared valid."""

    bounded = _BoundedPrefixReplayStream(
        stream,
        max_bytes=max_bytes,
        prefix_bytes=prefix_bytes,
    )
    detected = detect_upload(bounded.prefix, complete=bounded.prefix_is_complete)
    validated = _ValidatedUploadStream(bounded, detected)
    deferred = _DeferredDeclarationStream(
        validated,
        detected=detected,
        metadata_provider=metadata_provider,
        filename=filename,
        declared_content_type=declared_content_type,
    )
    stored = object_store.put_verified(deferred)
    if not validated.finished or deferred.metadata is None:
        raise UploadPolicyError(
            "INVALID_UPLOAD_STREAM",
            "object store did not consume the complete upload stream",
        )
    if stored.size_bytes == 0:
        raise UploadPolicyError("EMPTY_UPLOAD", "upload must contain at least one byte")
    return deferred.metadata, PreservedUpload(
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
    "preserve_upload_after_envelope",
    "validate_declared_upload",
]
