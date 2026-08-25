from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import darknetra_api.routes.evidence as evidence_route
import httpx
import pytest
import starlette.formparsers
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.config import Settings
from darknetra_api.db.session import get_db_session
from darknetra_api.dependencies.auth import get_current_auth_context
from darknetra_api.main import create_app
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.csrf import hash_csrf_token
from darknetra_api.storage.base import ObjectStore, StoredObject
from darknetra_api.storage.local import LocalObjectStore
from fastapi import HTTPException
from fastapi.testclient import TestClient


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, value: object) -> None:
        self.added.append(value)

    def add_all(self, values: list[object]) -> None:
        self.added.extend(values)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


class CapturingStore(ObjectStore):
    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.thread_ids: list[int] = []
        self.event_loop_thread_ids: list[int] = []

    def put_verified(self, stream, expected_sha256=None) -> StoredObject:
        del expected_sha256
        self.thread_ids.append(threading.get_ident())
        chunks = []
        while True:
            chunk = stream.read(11)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        self.payloads.append(payload)
        digest = hashlib.sha256(payload).hexdigest()
        return StoredObject(
            object_key=f"sha256/{digest[:2]}/{digest[2:4]}/{digest}",
            sha256=digest,
            size_bytes=len(payload),
        )

    def open(self, object_key: str):
        raise AssertionError(f"unexpected open: {object_key}")

    def verify(self, object_key: str, expected_sha256: str) -> bool:
        raise AssertionError(f"unexpected verify: {object_key} {expected_sha256}")


def settings(*, upload_max_bytes: int = 128) -> Settings:
    return Settings(
        field_key_v1_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
        field_blind_index_key_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
        evidence_upload_max_bytes=upload_max_bytes,
        _env_file=None,
    )


def metadata_json() -> str:
    return (
        '{"source_class":"SYNTHETIC","source_type":"TEXT",'
        '"acquisition_method":"fixture","captured_at":"2026-08-25T10:30:00Z",'
        '"source_locator":"https://example.test/private"}'
    )


def test_upload_openapi_describes_the_manual_multipart_contract() -> None:
    application = create_app(
        startup_settings_provider=settings,
        web_origin="https://web.example",
    )

    operation = application.openapi()["paths"]["/api/v1/cases/{case_id}/evidence"]["post"]
    request_body = operation["requestBody"]
    schema = request_body["content"]["multipart/form-data"]["schema"]

    assert request_body["required"] is True
    assert schema == {
        "type": "object",
        "additionalProperties": False,
        "required": ["metadata", "file"],
        "properties": {
            "metadata": {
                "type": "string",
                "description": "JSON-encoded evidence source metadata",
            },
            "file": {"type": "string", "format": "binary"},
        },
    }


@pytest.fixture
def upload_client(monkeypatch: pytest.MonkeyPatch):
    application = create_app(
        startup_settings_provider=settings,
        web_origin="https://web.example",
    )
    store = CapturingStore()
    session = FakeSession()
    csrf = "csrf-secret"
    user = User(
        id=uuid4(),
        username_normalized="collector",
        display_name="Collector",
        password_hash="not-used",
        global_roles=[GlobalRole.COLLECTOR],
        is_active=True,
        must_change_password=False,
    )
    context = SimpleNamespace(
        user=user,
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )

    async def db_provider() -> AsyncIterator[FakeSession]:
        yield session

    async def auth_provider():
        return context

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs
        store.event_loop_thread_ids.append(threading.get_ident())

    async def publisher(payload: dict[str, str]) -> None:
        assert session.committed
        assert set(payload) == {"job_id", "case_id", "evidence_id", "pipeline_version"}

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_db_session] = db_provider
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.state.evidence_object_store = store
    application.state.ingest_publisher = publisher
    with TestClient(application) as client:
        yield client, store, csrf


def test_upload_requires_authentication_and_csrf(upload_client) -> None:
    client, store, _ = upload_client

    response = client.post(
        f"/api/v1/cases/{uuid4()}/evidence",
        data={"metadata": metadata_json()},
        files={"file": ("note.txt", b"safe text", "text/plain")},
    )

    assert response.status_code == 403
    assert store.payloads == []


def test_malformed_metadata_and_early_content_length_do_not_reach_storage(upload_client) -> None:
    client, store, csrf = upload_client
    headers = {"X-CSRF-Token": csrf, "Content-Length": "1000000"}
    too_large = client.post(
        f"/api/v1/cases/{uuid4()}/evidence",
        headers=headers,
        data={"metadata": metadata_json()},
        files={"file": ("note.txt", b"safe text", "text/plain")},
    )
    malformed = client.post(
        f"/api/v1/cases/{uuid4()}/evidence",
        headers={"X-CSRF-Token": csrf},
        data={"metadata": "{broken"},
        files={"file": ("note.txt", b"safe text", "text/plain")},
    )

    assert too_large.status_code == 413
    assert too_large.json() == {"detail": {"code": "UPLOAD_TOO_LARGE"}}
    assert malformed.status_code == 422
    assert store.payloads == []


def test_successful_upload_returns_only_redacted_accepted_metadata(upload_client) -> None:
    client, store, csrf = upload_client
    payload = b"safe text\nsecond line\n"

    response = client.post(
        f"/api/v1/cases/{uuid4()}/evidence",
        headers={"X-CSRF-Token": csrf},
        data={"metadata": metadata_json()},
        files={"file": ("note.txt", payload, "text/plain")},
    )

    assert response.status_code == 202
    assert store.payloads == [payload]
    assert store.thread_ids
    assert store.event_loop_thread_ids
    assert set(store.thread_ids).isdisjoint(store.event_loop_thread_ids)
    body = response.json()
    assert body["evidence"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["evidence"]["state"] == "PRESERVED"
    assert body["job"]["status"] == "PENDING"
    serialized = response.text
    for forbidden in (
        "https://example.test/private",
        "object_key",
        "blind_index",
        "ciphertext",
        "nonce",
        "broker",
        "evidence-store",
    ):
        assert forbidden not in serialized


def test_unexpected_persistence_failure_returns_and_logs_only_redacted_error(
    upload_client,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, store, csrf = upload_client
    exception_secret = "ciphertext-and-blind-index-must-not-leak"

    async def fail_persistence(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(exception_secret)

    monkeypatch.setattr(evidence_route, "persist_preserved_upload", fail_persistence)
    caplog.set_level(logging.ERROR, logger=evidence_route.__name__)

    response = client.post(
        f"/api/v1/cases/{uuid4()}/evidence",
        headers={"X-CSRF-Token": csrf},
        data={"metadata": metadata_json()},
        files={"file": ("note.txt", b"orphaned safe text", "text/plain")},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "EVIDENCE_PERSISTENCE_FAILED"}}
    assert store.payloads == [b"orphaned safe text"]
    rendered = response.text + caplog.text
    for forbidden in (
        exception_secret,
        "https://example.test/private",
        "ciphertext",
        "blind_index",
        "object_key",
        "evidence-store",
        "redis://",
    ):
        assert forbidden not in rendered
    assert "code=EVIDENCE_PERSISTENCE_FAILED" in caplog.text
    assert "error_type=RuntimeError" in caplog.text


class CountingMultipartStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk


class PausingMultipartStream(httpx.AsyncByteStream):
    def __init__(self, opening: bytes) -> None:
        self.opening = opening
        self.paused = asyncio.Event()
        self.release = asyncio.Event()

    async def __aiter__(self):
        yield self.opening
        for _ in range(17):
            yield b"x" * 4096
        self.paused.set()
        await self.release.wait()


@pytest.mark.asyncio
async def test_asgi_receive_limit_cuts_off_chunked_multipart_before_parser_spooling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "stream-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )

    async def auth_provider():
        return context

    async def db_provider():
        yield FakeSession()

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = CapturingStore()
    boundary = "darknetra-stream-boundary"
    opening = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode()
    chunks = [opening, *([b"x" * 4096] * 64), f"\r\n--{boundary}--\r\n".encode()]
    stream = CountingMultipartStream(chunks)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
                "Origin": "https://web.example",
            },
            content=stream,
        )
        unrelated = await client.get(
            "/api/v1/health/live",
            headers={"Content-Length": "999999999"},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "UPLOAD_TOO_LARGE"}}
    assert stream.yielded < len(chunks)
    assert unrelated.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://web.example"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
async def test_oversized_epilogue_aborts_before_storage_commit_or_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    store = CapturingStore()
    session = FakeSession()
    published: list[dict[str, str]] = []
    csrf = "epilogue-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )

    async def auth_provider():
        return context

    async def db_provider():
        yield session

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    async def publisher(payload: dict[str, str]) -> None:
        published.append(payload)

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = store
    application.state.ingest_publisher = publisher

    boundary = "darknetra-epilogue-boundary"
    complete_parts = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="metadata"\r\n\r\n'
        f"{metadata_json()}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "ok\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    chunks = [complete_parts, *([b"x" * 4096] * 17)]
    stream = CountingMultipartStream(chunks)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
            content=stream,
        )

    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "UPLOAD_TOO_LARGE"}}
    assert stream.yielded < len(chunks)
    assert store.payloads == []
    assert session.added == []
    assert session.committed is False
    assert published == []


@pytest.mark.parametrize(
    ("denial", "csrf_header", "expected_status"),
    [
        ("unauthenticated", None, 401),
        ("bad_csrf", "wrong-csrf", 403),
        ("viewer", "preauth-csrf", 403),
        ("cross_case", "preauth-csrf", 404),
        ("nonexistent_case", "preauth-csrf", 404),
    ],
)
@pytest.mark.asyncio
async def test_auth_csrf_and_case_denials_do_not_consume_multipart_body(
    monkeypatch: pytest.MonkeyPatch,
    denial: str,
    csrf_header: str | None,
    expected_status: int,
) -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "preauth-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )

    async def auth_provider():
        if denial == "unauthenticated":
            raise HTTPException(status_code=401, detail="authentication required")
        return context

    async def db_provider():
        yield FakeSession()

    async def denied_authorization(*args, **kwargs) -> None:
        del args, kwargs
        if denial == "viewer":
            raise AuthorizationDenied("permission denied")
        if denial in {"cross_case", "nonexistent_case"}:
            raise CaseNotFound("resource not found")

    monkeypatch.setattr(evidence_route, "authorize_case", denied_authorization)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = CapturingStore()

    boundary = "darknetra-preauth-boundary"
    multipart = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="metadata"\r\n\r\n'
        f"{json.dumps({'payload': 'x' * 1024})}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        f"{'body' * 1024}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    chunks = [multipart[index : index + 256] for index in range(0, len(multipart), 256)]
    stream = CountingMultipartStream(chunks)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if csrf_header is not None:
        headers["X-CSRF-Token"] = csrf_header
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers=headers,
            content=stream,
        )

    assert response.status_code == expected_status
    assert stream.yielded == 0


@pytest.mark.asyncio
async def test_file_limit_plus_one_stops_body_producer_before_later_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = settings(upload_max_bytes=1024 * 1024)
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "file-limit-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )
    session = FakeSession()
    store = CapturingStore()

    async def auth_provider():
        return context

    async def db_provider():
        yield session

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = store

    boundary = "darknetra-file-limit-boundary"
    opening = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="metadata"\r\n\r\n'
        f"{metadata_json()}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode()
    chunks = [
        opening,
        *([b"x" * 4096] * 256),
        b"x",
        *([b"later" * 819] * 10),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    assert sum(map(len, chunks)) < runtime.evidence_upload_max_bytes + 64 * 1024
    stream = CountingMultipartStream(chunks)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
            content=stream,
        )

    assert response.status_code == 413
    assert response.json() == {"detail": {"code": "UPLOAD_TOO_LARGE"}}
    assert stream.yielded < len(chunks)
    assert store.payloads == []
    assert session.added == []
    assert session.committed is False


@pytest.mark.asyncio
async def test_valid_upload_does_not_use_starlette_spooled_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "no-spool-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )
    store = CapturingStore()

    async def auth_provider():
        return context

    async def db_provider():
        yield FakeSession()

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    def forbid_spool(*args, **kwargs):
        del args, kwargs
        raise AssertionError("multipart file spooling is forbidden")

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", forbid_spool)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = store
    application.state.ingest_publisher = lambda payload: None
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={"X-CSRF-Token": csrf},
            data={"metadata": metadata_json()},
            files={"file": ("note.txt", b"direct staged text", "text/plain")},
        )

    assert response.status_code == 202
    assert store.payloads == [b"direct staged text"]


def malformed_multipart(variant: str) -> tuple[str, bytes, str]:
    boundary = "darknetra-malformed-boundary"
    attacker_marker = "ATTACKER-MULTIPART-MARKER"
    if variant == "boundary_size":
        boundary = "b" * 257
        body = f"--{boundary}--\r\n".encode()
    elif variant == "header_size":
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="'
            f'{attacker_marker * 220}.txt"\r\n\r\nx\r\n--{boundary}--\r\n'
        ).encode()
    elif variant == "header_count":
        headers = "".join(f"X-Header-{index}: value\r\n" for index in range(8))
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="metadata"\r\n'
            f"{headers}\r\n{{}}\r\n--{boundary}--\r\n"
        ).encode()
    elif variant == "malformed_header":
        body = (
            f"--{boundary}\r\n{attacker_marker} without-colon\r\n\r\nx\r\n--{boundary}--\r\n"
        ).encode()
    elif variant == "after_file":
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
            "Content-Type: text/plain\r\n\r\ndirect staged text\r\n"
            f"--{boundary}\r\n"
            f"{attacker_marker} without-colon\r\n\r\nx\r\n--{boundary}--\r\n"
        ).encode()
    else:  # pragma: no cover - test helper guard
        raise AssertionError(variant)
    return boundary, body, attacker_marker


@pytest.mark.parametrize(
    "variant",
    ["boundary_size", "header_size", "header_count", "malformed_header"],
)
@pytest.mark.asyncio
async def test_raw_multipart_parser_failures_are_stable_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    variant: str,
) -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "malformed-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )

    async def auth_provider():
        return context

    async def db_provider():
        yield FakeSession()

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = CapturingStore()
    boundary, body, attacker_marker = malformed_multipart(variant)
    caplog.set_level(logging.WARNING)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
            content=body,
        )

    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "INVALID_MULTIPART"}}
    assert attacker_marker not in response.text + caplog.text


@pytest.mark.asyncio
async def test_parser_failure_after_file_start_cleans_object_store_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "after-file-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )
    store = LocalObjectStore(
        tmp_path,
        allow_trusted_volume_fallback=os.name == "nt",
    )

    async def auth_provider():
        return context

    async def db_provider():
        yield FakeSession()

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = store
    boundary, body, _ = malformed_multipart("after_file")
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-CSRF-Token": csrf,
            },
            content=body,
        )

    assert response.status_code == 400
    assert response.json() == {"detail": {"code": "INVALID_MULTIPART"}}
    assert list((tmp_path / ".staging").iterdir()) == []
    assert list((tmp_path / "sha256").rglob("*")) == []


@pytest.mark.asyncio
async def test_cancelled_upload_aborts_worker_and_removes_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = settings(upload_max_bytes=1024 * 1024)
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    application.state.sensitive_field_crypto = runtime.require_sensitive_field_crypto()
    csrf = "cancel-csrf"
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        auth_session=SimpleNamespace(csrf_token_hash=hash_csrf_token(csrf)),
    )
    store = LocalObjectStore(
        tmp_path,
        allow_trusted_volume_fallback=os.name == "nt",
    )

    async def auth_provider():
        return context

    async def db_provider():
        yield FakeSession()

    async def authorized(*args, **kwargs) -> None:
        del args, kwargs

    monkeypatch.setattr(evidence_route, "authorize_case", authorized)
    application.dependency_overrides[get_current_auth_context] = auth_provider
    application.dependency_overrides[get_db_session] = db_provider
    application.state.evidence_object_store = store
    boundary = "darknetra-cancel-boundary"
    opening = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="metadata"\r\n\r\n'
        f"{metadata_json()}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="cancel.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode()
    stream = PausingMultipartStream(opening)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        request_task = asyncio.create_task(
            client.post(
                f"/api/v1/cases/{uuid4()}/evidence",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "X-CSRF-Token": csrf,
                },
                content=stream,
            )
        )
        await asyncio.wait_for(stream.paused.wait(), timeout=2)
        for _ in range(200):
            if list((tmp_path / ".staging").iterdir()):
                break
            await asyncio.sleep(0.01)
        else:
            request_task.cancel()
            raise AssertionError("direct object-store staging did not begin")
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

    assert list((tmp_path / ".staging").iterdir()) == []
    assert list((tmp_path / "sha256").rglob("*")) == []


@pytest.mark.asyncio
async def test_early_content_length_limit_uses_configured_cors_only() -> None:
    runtime = settings()
    application = create_app(
        startup_settings_provider=lambda: runtime,
        web_origin="https://web.example",
    )
    application.state.runtime_settings = runtime
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        allowed = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Length": "999999",
                "Origin": "https://web.example",
            },
        )
        untrusted = await client.post(
            f"/api/v1/cases/{uuid4()}/evidence",
            headers={
                "Content-Length": "999999",
                "Origin": "https://untrusted.example",
            },
        )

    assert allowed.status_code == untrusted.status_code == 413
    assert allowed.headers["access-control-allow-origin"] == "https://web.example"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in untrusted.headers
