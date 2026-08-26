from __future__ import annotations

import base64
import json

import pytest
from darknetra_api.routes.intelligence import list_integrations_route, normalize_integration_route
from darknetra_api.schemas.intelligence import IntegrationNormalizeRequest


@pytest.mark.asyncio
async def test_integration_route_exposes_adapter_capabilities_without_execution_secrets() -> None:
    response = await list_integrations_route(user=object())

    robin = next(item for item in response.items if item.slug == "robin")
    torbot = next(item for item in response.items if item.slug == "torbot")
    assert robin.integration_mode == "IMPORT"
    assert "report" in robin.accepted_outputs
    assert torbot.accepted_outputs == ["json-link-tree"]
    serialized = response.model_dump_json().lower()
    assert "api_key" not in serialized
    assert ".onion" not in serialized


@pytest.mark.asyncio
async def test_normalize_route_turns_torbot_output_into_hashed_observations() -> None:
    root_url = f"http://{'b' * 56}.onion/root"
    child_url = f"http://{'c' * 56}.onion/thread"
    payload = json.dumps(
        {
            "url": root_url,
            "title": "Root",
            "children": [{"url": child_url, "title": "Thread", "children": []}],
        }
    ).encode()

    response = await normalize_integration_route(
        adapter="torbot",
        payload=IntegrationNormalizeRequest(
            source_name="Authorized TorBot import",
            payload_base64=base64.b64encode(payload).decode(),
        ),
        user=object(),
    )

    assert response.adapter == "torbot"
    assert (
        response.content_sha256
        == "c5e4324fa0b9eda1bded517e4ef04e2cc9db477587f20018964cac7a8c3cb8ae"
    )
    assert [(item.kind, item.value, item.parent) for item in response.observations] == [
        ("PAGE", root_url, None),
        ("LINK", child_url, root_url),
    ]


def test_normalize_request_rejects_packages_larger_than_two_megabytes() -> None:
    with pytest.raises(ValueError):
        IntegrationNormalizeRequest(
            source_name="Oversized package",
            payload_base64=base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode(),
        )
