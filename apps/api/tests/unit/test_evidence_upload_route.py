from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

import darknetra_api.routes.evidence as evidence_route
import httpx
import pytest
from darknetra_api.config import Settings
from darknetra_api.db.session import get_db_session
from darknetra_api.dependencies.auth import get_current_auth_context
from darknetra_api.main import create_app
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.csrf import hash_csrf_token
from darknetra_api.storage.base import ObjectStore, StoredObject
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


def settings() -> Settings:
    return Settings(
        field_key_v1_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
        field_blind_index_key_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
        evidence_upload_max_bytes=128,
        _env_file=None,
    )


def metadata_json() -> str:
    return (
        '{"source_class":"SYNTHETIC","source_type":"TEXT",'
        '"acquisition_method":"fixture","captured_at":"2026-08-25T10:30:00Z",'
        '"source_locator":"https://example.test/private"}'
    )


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


class CountingMultipartStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk


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
