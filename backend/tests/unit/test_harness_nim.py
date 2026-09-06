import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel

from darknetra.agent.harness_nim import NimHarness
from darknetra.auth.actor import Actor
from darknetra.config import Settings
from darknetra.tools.contracts import AgentRole, Lane, ToolContext, ToolResult, ToolSpec


class LookupInput(BaseModel):
    term: str


class LookupOutput(BaseModel):
    answer: str


async def unused_impl(ctx, data):  # pragma: no cover
    raise AssertionError("invoke owns execution")


SPEC = ToolSpec(
    name="lookup",
    description="Search captured evidence",
    input_model=LookupInput,
    output_model=LookupOutput,
    lane=Lane.EVIDENCE,
    impl=unused_impl,
    allowed_for=frozenset({AgentRole.CASE_LEAD}),
)


def settings(**overrides):
    material = base64.b64encode(b"s" * 32).decode()
    values = dict(
        _env_file=None,
        database_url="postgresql+psycopg://synthetic",
        jwt_signing_key_b64=material,
        field_key_b64=material,
        nim_base_url="https://nim.test/v1",
        nim_model="meta/model",
        nim_input_cost_per_million=0,
        nim_output_cost_per_million=0,
    )
    values.update(overrides)
    return Settings(**values)


def context(config):
    return ToolContext(uuid4(), Actor("USER", uuid4()), SimpleNamespace(), config)


@pytest.mark.asyncio
async def test_nim_executes_role_tool_through_invoke(monkeypatch):
    requests = []

    async def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "lookup",
                                            "arguments": '{"term":"wallet"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Found E-0001."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    invoke = AsyncMock(return_value=ToolResult(ok=True, data={"answer": "E-0001"}))
    monkeypatch.setattr("darknetra.agent.harness_nim.for_role", lambda role: [SPEC])
    monkeypatch.setattr("darknetra.agent.harness_nim.invoke", invoke)
    transport = httpx.MockTransport(handler)

    events = [
        event
        async for event in NimHarness(transport=transport).run(context(settings()), "Find wallet")
    ]

    assert events[-1] == {"type": "assistant", "text": "Found E-0001."}
    assert requests[0]["tools"][0]["function"]["name"] == "lookup"
    assert requests[0]["max_tokens"] == 4096
    assert requests[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"ok":true,"data":{"answer":"E-0001"},"error":null,"evidence_ids":[],"truncated":false}',
    }
    invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_nim_unknown_tool_is_denied_without_invocation(monkeypatch):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "x",
                                        "type": "function",
                                        "function": {"name": "not_registered", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )
        payload = json.loads(request.content)
        assert json.loads(payload["messages"][-1]["content"])["error"]["code"] == "POLICY_DENIED"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Insufficient evidence."}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    invoke = AsyncMock()
    monkeypatch.setattr("darknetra.agent.harness_nim.for_role", lambda role: [SPEC])
    monkeypatch.setattr("darknetra.agent.harness_nim.invoke", invoke)
    events = [
        event
        async for event in NimHarness(transport=httpx.MockTransport(handler)).run(
            context(settings()), "x"
        )
    ]
    assert events[-1]["text"] == "Insufficient evidence."
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_nim_requires_rates_before_spending(monkeypatch):
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Done"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
        )

    monkeypatch.setattr("darknetra.agent.harness_nim.for_role", lambda role: [])
    from darknetra.tools.contracts import ToolError

    with pytest.raises(ToolError, match="Configure NIM token rates"):
        [
            event
            async for event in NimHarness(transport=httpx.MockTransport(handler)).run(
                context(
                    settings(nim_input_cost_per_million=None, nim_output_cost_per_million=None)
                ),
                "x",
            )
        ]


@pytest.mark.asyncio
async def test_nim_uses_worker_model_and_configured_token_rates(monkeypatch):
    seen = {}

    async def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Done"}}],
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
            },
        )

    monkeypatch.setattr("darknetra.agent.harness_nim.for_role", lambda role: [])
    ctx = context(
        settings(
            nim_worker_model="worker/model",
            nim_input_cost_per_million=2,
            nim_output_cost_per_million=4,
        )
    )
    ctx.role = AgentRole.EVIDENCE_ANALYST
    events = [
        event
        async for event in NimHarness(transport=httpx.MockTransport(handler)).run(
            ctx, "x", budget=10
        )
    ]
    assert seen["model"] == "worker/model"
    assert events[0]["cost_usd"] == 4.0
    assert events[0]["cost_complete"] is True
