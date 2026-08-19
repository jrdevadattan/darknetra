from __future__ import annotations

from datetime import UTC, datetime

import pytest
from darknetra_api.policy import ingestion
from pydantic import ValidationError


def metadata_payload(source_class: str = "SYNTHETIC") -> dict[str, object]:
    return {
        "source_class": source_class,
        "source_type": "synthetic.fixture",
        "acquisition_method": "authorized_test_generation",
        "captured_at": datetime.now(UTC),
        "original_timezone": "UTC",
    }


def test_limits_default_to_100_mib_with_an_absolute_500_mib_ceiling() -> None:
    limits = ingestion.IngestionLimits()
    assert limits.max_upload_bytes == 100 * 1024 * 1024
    assert limits.hard_ceiling_bytes == 500 * 1024 * 1024
    with pytest.raises(ValueError, match="hard ceiling"):
        ingestion.IngestionLimits(max_upload_bytes=501 * 1024 * 1024)
    with pytest.raises(ValueError, match="absolute hard ceiling"):
        ingestion.IngestionLimits(hard_ceiling_bytes=501 * 1024 * 1024)
    with pytest.raises(ValueError, match="positive"):
        ingestion.IngestionLimits(max_upload_bytes=0)


@pytest.mark.parametrize("source_class", ["PUBLIC_OBSERVATION", "AUTHORIZED_IMPORT"])
def test_governed_sources_require_an_authority_reference(source_class: str) -> None:
    with pytest.raises(ValidationError, match="authority_reference"):
        ingestion.EvidenceSourceMetadata.model_validate(metadata_payload(source_class))

    payload = metadata_payload(source_class)
    payload["authority_reference"] = "AUTH-REF-001"
    parsed = ingestion.EvidenceSourceMetadata.model_validate(payload)
    assert parsed.authority_reference == "AUTH-REF-001"


@pytest.mark.parametrize("source_class", ["SYNTHETIC", "RESEARCH_ARCHIVE"])
def test_non_live_sources_do_not_invent_an_authority_reference(source_class: str) -> None:
    parsed = ingestion.EvidenceSourceMetadata.model_validate(metadata_payload(source_class))
    assert parsed.authority_reference is None


def test_metadata_rejects_naive_capture_time_and_unknown_fields() -> None:
    naive = metadata_payload()
    naive["captured_at"] = "2026-08-19T10:30:00"
    with pytest.raises(ValidationError, match="timezone-aware"):
        ingestion.EvidenceSourceMetadata.model_validate(naive)

    extra = metadata_payload()
    extra["uploaded_filename"] = "do-not-trust.exe"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ingestion.EvidenceSourceMetadata.model_validate(extra)


def test_declared_length_is_rejected_before_streaming_when_over_limit() -> None:
    limits = ingestion.IngestionLimits(max_upload_bytes=128)
    assert ingestion.validate_content_length(None, limits=limits) is None
    assert ingestion.validate_content_length("128", limits=limits) == 128
    with pytest.raises(ingestion.UploadSizeExceeded, match="128"):
        ingestion.validate_content_length("129", limits=limits)
    with pytest.raises(ingestion.InvalidContentLength):
        ingestion.validate_content_length("not-a-number", limits=limits)
    with pytest.raises(ingestion.InvalidContentLength):
        ingestion.validate_content_length("-1", limits=limits)


@pytest.mark.parametrize(
    ("payload", "media_type", "family"),
    [
        (b"%PDF-1.7\n", "application/pdf", "pdf"),
        (b"\x89PNG\r\n\x1a\nrest", "image/png", "image"),
        (b"\xff\xd8\xff\xe0rest", "image/jpeg", "image"),
        (b"RIFF\x10\x00\x00\x00WEBPrest", "image/webp", "image"),
        (b"PK\x03\x04rest", "application/zip", "archive"),
        (b"WARC/1.1\r\nWARC-Type: response\r\n", "application/warc", "warc"),
        (b"\x1f\x8b\x08\x00rest", "application/gzip", "warc_gzip_candidate"),
        (b"<!doctype html><html><body>safe</body></html>", "text/html", "html"),
        (b'{"messages": [{"text": "safe"}]}', "application/json", "json"),
        (b"plain UTF-8 evidence text\n", "text/plain", "text"),
    ],
)
def test_byte_signatures_select_only_allowlisted_parser_families(
    payload: bytes,
    media_type: str,
    family: str,
) -> None:
    detected = ingestion.detect_media_type(payload)
    assert detected.media_type == media_type
    assert detected.parser_family == family


def test_csv_requires_textual_bytes_and_an_explicit_csv_declaration() -> None:
    payload = b"vendor,price,quantity\nalpha,10,1\n"
    generic = ingestion.detect_media_type(payload)
    assert generic.media_type == "text/plain"
    detected = ingestion.detect_media_type(
        payload,
        declared_media_type="text/csv; charset=utf-8",
    )
    assert detected.media_type == "text/csv"
    assert detected.parser_family == "csv"


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x7fELF\x02\x01\x01\x00",
        b"MZ\x90\x00\x03\x00",
        b"#!/bin/sh\necho unsafe\n",
        b"text\x00with-nul",
        b"\xff\xfe\xfd\xfc",
    ],
)
def test_empty_binary_and_executable_payloads_are_rejected(payload: bytes) -> None:
    with pytest.raises(ingestion.UnsupportedMediaType):
        ingestion.detect_media_type(payload)


def test_concrete_declared_mime_must_match_detected_bytes() -> None:
    with pytest.raises(ingestion.MediaTypeMismatch):
        ingestion.detect_media_type(
            b"%PDF-1.7\n",
            declared_media_type="image/png",
        )
    detected = ingestion.detect_media_type(
        b"%PDF-1.7\n",
        declared_media_type="application/octet-stream",
    )
    assert detected.media_type == "application/pdf"


def test_malformed_json_declared_as_json_is_not_silently_accepted_as_text() -> None:
    with pytest.raises(ingestion.MediaTypeMismatch):
        ingestion.detect_media_type(
            b'{"messages": [}',
            declared_media_type="application/json",
        )
