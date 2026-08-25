from __future__ import annotations

import gzip
import hashlib
import io

import pytest
from darknetra_api.models.evidence import EvidenceSourceClass
from darknetra_api.policy.ingestion import (
    EvidenceSourceMetadata,
    EvidenceSourceType,
    PreservedUpload,
    UploadPolicyError,
    preserve_upload,
)
from darknetra_api.storage.base import StoredObject


class RecordingStream(io.BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        assert size > 0, "upload policy must never request an unbounded read"
        self.read_sizes.append(size)
        return super().read(size)


class CapturingStore:
    def __init__(self) -> None:
        self.payload = b""

    def put_verified(self, stream, expected_sha256=None) -> StoredObject:
        chunks: list[bytes] = []
        while True:
            chunk = stream.read(7)
            if chunk == b"":
                break
            chunks.append(chunk)
        self.payload = b"".join(chunks)
        digest = hashlib.sha256(self.payload).hexdigest()
        assert expected_sha256 is None
        return StoredObject(
            object_key=f"sha256/{digest[:2]}/{digest[2:4]}/{digest}",
            sha256=digest,
            size_bytes=len(self.payload),
        )


def metadata(source_type: EvidenceSourceType) -> EvidenceSourceMetadata:
    extra = {}
    if source_type in {EvidenceSourceType.WARC, EvidenceSourceType.WARC_GZ}:
        extra["source_locator"] = "https://example.test/archive"
    return EvidenceSourceMetadata.model_validate(
        {
            "source_class": EvidenceSourceClass.SYNTHETIC,
            "source_type": source_type,
            "acquisition_method": "test fixture",
            "captured_at": "2026-08-25T10:30:00+05:30",
            **extra,
        }
    )


@pytest.mark.parametrize(
    ("payload", "source_type", "filename", "content_type", "media_type"),
    [
        (b"WARC/1.1\r\nWARC-Type: response\r\n", EvidenceSourceType.WARC, "a.warc", "application/warc", "application/warc"),
        (gzip.compress(b"WARC/1.1\r\nWARC-Type: response\r\n"), EvidenceSourceType.WARC_GZ, "a.warc.gz", "application/gzip", "application/warc+gzip"),
        (b"<!doctype html><html><body>x</body></html>", EvidenceSourceType.HTML, "a.html", "text/html", "text/html"),
        (b"<?xml version='1.0'?><html xmlns='http://www.w3.org/1999/xhtml'/>", EvidenceSourceType.XHTML, "a.xhtml", "application/xhtml+xml", "application/xhtml+xml"),
        (b"ordinary utf-8 text\nsecond line\n", EvidenceSourceType.TEXT, "a.txt", "text/plain", "text/plain"),
        (b'{"ok":true}', EvidenceSourceType.JSON, "a.json", "application/json", "application/json"),
        (b"name,count\nalice,2\n", EvidenceSourceType.CSV, "a.csv", "text/csv", "text/csv"),
        (b"PK\x03\x04" + b"x" * 32, EvidenceSourceType.ZIP, "a.zip", "application/zip", "application/zip"),
        (b"\x89PNG\r\n\x1a\n" + b"x" * 32, EvidenceSourceType.PNG, "a.png", "image/png", "image/png"),
        (b"\xff\xd8\xff\xe0" + b"x" * 32, EvidenceSourceType.JPEG, "a.jpg", "image/jpeg", "image/jpeg"),
        (b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"x" * 16, EvidenceSourceType.WEBP, "a.webp", "image/webp", "image/webp"),
        (b"%PDF-1.7\n1 0 obj\n", EvidenceSourceType.PDF, "a.pdf", "application/pdf", "application/pdf"),
    ],
)
def test_supported_bytes_are_classified_and_prefix_is_replayed_exactly(
    payload: bytes,
    source_type: EvidenceSourceType,
    filename: str,
    content_type: str,
    media_type: str,
) -> None:
    stream = RecordingStream(payload)
    store = CapturingStore()

    result = preserve_upload(
        stream=stream,
        object_store=store,
        metadata=metadata(source_type),
        filename=filename,
        declared_content_type=content_type,
        max_bytes=1024,
        prefix_bytes=64,
    )

    assert result.media_type == media_type
    assert result.stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.stored.size_bytes == len(payload)
    assert store.payload == payload
    assert stream.read_sizes and max(stream.read_sizes) <= 64


def test_streaming_limit_aborts_at_limit_plus_one_without_whole_file_read() -> None:
    stream = RecordingStream(b"a" * 101)

    with pytest.raises(UploadPolicyError) as caught:
        preserve_upload(
            stream=stream,
            object_store=CapturingStore(),
            metadata=metadata(EvidenceSourceType.TEXT),
            filename="a.txt",
            declared_content_type="text/plain",
            max_bytes=100,
            prefix_bytes=16,
        )

    assert caught.value.code == "UPLOAD_TOO_LARGE"
    assert stream.tell() == 101
    assert -1 not in stream.read_sizes


@pytest.mark.parametrize(
    ("payload", "source_type", "filename", "content_type", "code"),
    [
        (b"", EvidenceSourceType.TEXT, "a.txt", "text/plain", "EMPTY_UPLOAD"),
        (b"MZ" + b"x" * 32, EvidenceSourceType.TEXT, "a.txt", "text/plain", "UNSUPPORTED_MEDIA_TYPE"),
        (b"\x7fELF" + b"x" * 32, EvidenceSourceType.TEXT, "a.txt", "text/plain", "UNSUPPORTED_MEDIA_TYPE"),
        (b"\x00\x01\x02\x03" * 8, EvidenceSourceType.TEXT, "a.txt", "text/plain", "UNSUPPORTED_MEDIA_TYPE"),
        (b"%PDF-1.7\n", EvidenceSourceType.PDF, "a.png", "application/pdf", "FILENAME_TYPE_MISMATCH"),
        (b"%PDF-1.7\n", EvidenceSourceType.PDF, "a.pdf", "image/png", "DECLARED_MIME_MISMATCH"),
        (b"%PDF-1.7\n", EvidenceSourceType.PNG, "a.pdf", "application/pdf", "SOURCE_TYPE_MISMATCH"),
        (b"{broken", EvidenceSourceType.JSON, "a.json", "application/json", "MALFORMED_MEDIA"),
        (b"\x1f\x8bbroken", EvidenceSourceType.WARC_GZ, "a.warc.gz", "application/gzip", "MALFORMED_MEDIA"),
    ],
)
def test_invalid_or_spoofed_upload_is_rejected_before_storage(
    payload: bytes,
    source_type: EvidenceSourceType,
    filename: str,
    content_type: str,
    code: str,
) -> None:
    store = CapturingStore()

    with pytest.raises(UploadPolicyError) as caught:
        preserve_upload(
            stream=RecordingStream(payload),
            object_store=store,
            metadata=metadata(source_type),
            filename=filename,
            declared_content_type=content_type,
            max_bytes=1024,
            prefix_bytes=64,
        )

    assert caught.value.code == code
    assert store.payload == b""


def test_authority_reference_is_required_for_governed_source_classes() -> None:
    for source_class in (
        EvidenceSourceClass.PUBLIC_OBSERVATION,
        EvidenceSourceClass.AUTHORIZED_IMPORT,
    ):
        with pytest.raises(ValueError):
            EvidenceSourceMetadata.model_validate(
                {
                    "source_class": source_class,
                    "source_type": "TEXT",
                    "acquisition_method": "approved import",
                    "captured_at": "2026-08-25T10:30:00Z",
                    "authority_reference": "  ",
                }
            )


def test_captured_at_requires_an_explicit_timezone() -> None:
    with pytest.raises(ValueError):
        EvidenceSourceMetadata.model_validate(
            {
                "source_class": "SYNTHETIC",
                "source_type": "TEXT",
                "acquisition_method": "test fixture",
                "captured_at": "2026-08-25T10:30:00",
            }
        )


def test_sensitive_metadata_and_storage_path_are_redacted_from_repr() -> None:
    protected = EvidenceSourceMetadata.model_validate(
        {
            "source_class": "PUBLIC_OBSERVATION",
            "source_type": "TEXT",
            "acquisition_method": "fixture",
            "captured_at": "2026-08-25T10:30:00Z",
            "source_locator": "https://secret.example/path",
            "authority_reference": "secret authority",
            "protected_note": "secret note",
        }
    )
    result = PreservedUpload(
        stored=StoredObject(
            object_key="sha256/aa/aa/" + "a" * 64,
            sha256="a" * 64,
            size_bytes=1,
        ),
        media_type="text/plain",
        parser_family="text",
    )

    serialized = repr(protected) + repr(result)
    assert "secret.example" not in serialized
    assert "secret authority" not in serialized
    assert "secret note" not in serialized
    assert "sha256/aa/aa" not in serialized
