import asyncio
import base64
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from darknetra.auth.actor import Actor
from darknetra.config import Settings
from darknetra.tools.contracts import AgentRole, Lane, ToolContext, ToolSpec
from darknetra.tools.invoke import invoke


@pytest.fixture
def ctx():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        jwt_signing_key_b64=base64.b64encode(b"a" * 32).decode(),
        field_key_b64=base64.b64encode(b"b" * 32).decode(),
    )
    return ToolContext(uuid4(), Actor("USER", uuid4()), MagicMock(), settings, emit=AsyncMock())


@pytest.fixture
def invocation(monkeypatch):
    from darknetra.tools import invoke as module

    monkeypatch.setattr(module, "check", AsyncMock())
    persisted = AsyncMock()
    monkeypatch.setattr(module, "persist", persisted)
    return persisted


class Args(BaseModel):
    query: str


class Output(BaseModel):
    text: str


async def response(ctx, args):
    return Output(text=str(ctx.case_id) + ":" + args.query)


def spec(**overrides):
    return replace(
        ToolSpec(
            "test_evidence",
            "SYNTHETIC test",
            Args,
            Output,
            Lane.EVIDENCE,
            response,
            frozenset({AgentRole.CASE_LEAD}),
        ),
        **overrides,
    )


async def test_model_case_id_is_ignored(ctx, invocation, monkeypatch):
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "test_evidence", spec())
    result = await invoke(ctx, "test_evidence", {"query": "SYNTHETIC", "case_id": str(uuid4())})
    assert result.ok
    assert result.data["text"] == str(ctx.case_id) + ":SYNTHETIC"


async def test_validation_is_audited_without_sensitive_args(ctx, invocation, monkeypatch):
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "test_evidence", spec())
    result = await invoke(ctx, "test_evidence", {"unrecognized": "SYNTHETIC secret"})
    assert not result.ok and result.error["code"] == "VALIDATION"
    assert invocation.call_count == 1
    assert "SYNTHETIC secret" not in str(invocation.call_args)


async def test_timeout_returns_tool_error_and_emits_step(ctx, invocation, monkeypatch):
    from darknetra.tools.registry import REGISTRY

    async def slow(ctx, args):
        await asyncio.sleep(1)
        return Output(text="late")

    monkeypatch.setitem(REGISTRY, "test_evidence", spec(impl=slow, timeout_s=0.001))
    result = await invoke(ctx, "test_evidence", {"query": "SYNTHETIC"})
    assert not result.ok and result.error["code"] == "UNAVAILABLE"
    assert ctx.emit.call_args.args[0]["data"]["status"] == "error"


async def test_cache_does_not_repeat_tool_side_effect(ctx, invocation, monkeypatch):
    from darknetra.tools.registry import REGISTRY

    calls = []

    async def execute(ctx, args):
        calls.append(args.query)
        return Output(text="SYNTHETIC")

    monkeypatch.setitem(REGISTRY, "test_evidence", spec(impl=execute))
    first = await invoke(ctx, "test_evidence", {"query": "SYNTHETIC"})
    second = await invoke(ctx, "test_evidence", {"query": "SYNTHETIC"})
    assert first == second
    assert calls == ["SYNTHETIC"]


async def test_role_denial_before_impl(ctx, invocation, monkeypatch):
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(
        REGISTRY, "test_evidence", spec(allowed_for=frozenset({AgentRole.DARK_SCOUT}))
    )
    result = await invoke(ctx, "test_evidence", {"query": "SYNTHETIC"})
    assert result.error["code"] == "POLICY_DENIED"


async def test_oversize_result_is_bounded(ctx, invocation, monkeypatch):
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "test_evidence", spec(max_result_chars=10))
    result = await invoke(ctx, "test_evidence", {"query": "SYNTHETIC"})
    assert result.ok and result.truncated
    assert "text" not in result.data
