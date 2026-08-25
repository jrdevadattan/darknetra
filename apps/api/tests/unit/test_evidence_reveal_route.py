from __future__ import annotations

import secrets
from types import SimpleNamespace
from uuid import uuid4

import darknetra_api.routes.evidence as evidence_route
import pytest
from darknetra_api.schemas.evidence import SensitiveValueRevealRequest
from darknetra_api.security.encryption import SensitiveFieldCrypto
from fastapi import FastAPI, Response
from starlette.requests import Request


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": secrets.token_bytes(32)},
        active_key_version="v1",
        blind_index_key=secrets.token_bytes(32),
    )


@pytest.mark.asyncio
async def test_reveal_http_boundary_sets_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    application = FastAPI()
    application.state.sensitive_field_crypto = crypto()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "app": application,
        }
    )
    response = Response()
    session = SimpleNamespace(info={})
    monkeypatch.setattr(evidence_route, "_require_csrf", lambda request, context: None)

    captured: dict[str, object] = {}

    async def fake_reveal(**kwargs: object) -> str:
        captured.update(kwargs)
        return "explicit plaintext"

    monkeypatch.setattr(evidence_route, "reveal_sensitive_value", fake_reveal)
    case_id = uuid4()
    evidence_id = uuid4()
    result = await evidence_route.reveal_evidence_sensitive_value_route(
        case_id=case_id,
        evidence_id=evidence_id,
        field_name="source_locator",
        payload=SensitiveValueRevealRequest(reason="Validate source provenance"),
        request=request,
        response=response,
        context=SimpleNamespace(user=object()),
        db=session,
    )

    assert result.value == "explicit plaintext"
    assert response.headers["Cache-Control"] == "no-store"
    assert set(captured) == {
        "actor",
        "case_id",
        "resource_type",
        "resource_id",
        "field_name",
        "reason",
        "session",
    }
    assert captured["resource_id"] == str(evidence_id)
