"""SYNTHETIC tool activity lifecycle and capture persistence ordering."""

import asyncio
import importlib
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from darknetra.auth.actor import Actor
from darknetra.capture.fetcher import Fetched
from darknetra.tools.contracts import AgentRole, Lane, ToolContext, ToolError, ToolResult, ToolSpec

invoke_module = importlib.import_module("darknetra.tools.invoke")
gate = importlib.import_module("darknetra.capture.gate")


class Input(BaseModel):
    query: str


class Output(BaseModel):
    evidence_id: UUID
    evidence_code: str


@pytest.fixture
def tool_context(monkeypatch):
    events = []

    async def emit(event):
        if event["type"] == "activity.updated":
            from darknetra.api.v1.schemas.activity import ActivityUpdate

            ActivityUpdate.model_validate(event["data"])
        events.append(event)

    ctx = ToolContext(
        uuid4(),
        Actor("MODEL", None),
        None,
        None,
        thread_id=uuid4(),
        run_id=uuid4(),
        agent_id=uuid4(),
        emit=emit,
    )
    persisted = AsyncMock()
    monkeypatch.setattr(invoke_module, "persist", persisted)
    monkeypatch.setattr(invoke_module, "check", AsyncMock())
    return ctx, events, persisted


def register(monkeypatch, impl):
    spec = ToolSpec(
        "synthetic_tool",
        "SYNTHETIC test",
        Input,
        Output,
        Lane.EVIDENCE,
        impl,
        frozenset({AgentRole.CASE_LEAD}),
    )
    monkeypatch.setitem(invoke_module.REGISTRY, spec.name, spec)
    return spec


async def test_repeated_and_cached_calls_have_unique_stable_ids(tool_context, monkeypatch):
    ctx, events, persisted = tool_context
    evidence = uuid4()
    impl_contexts = []

    async def impl(bound, args):
        impl_contexts.append(bound)
        return Output(evidence_id=evidence, evidence_code="E-0042")

    register(monkeypatch, impl)
    for _ in range(2):
        result = await invoke_module.invoke(ctx, "synthetic_tool", {"query": "SYNTHETIC secret"})
        assert result.ok
    activity = [e["data"] for e in events if e["type"] == "activity.updated"]
    terminal = [e for e in activity if e["status"] == "completed"]
    assert len(terminal) == 2
    assert len({e["id"] for e in terminal}) == 2
    assert terminal[1]["phase"] == "cache_hit"
    assert terminal[0]["evidence_ids"] == [str(evidence)]
    assert terminal[0]["evidence_codes"] == ["E-0042"]
    assert all(e["parent_id"] == str(ctx.agent_id) for e in activity)
    assert impl_contexts[0].parent_call_id == UUID(terminal[0]["id"])
    assert ctx.parent_call_id is None
    assert len(impl_contexts) == 1
    assert persisted.await_count == 2
    assert "SYNTHETIC secret" not in json.dumps(events)
    steps = [e["data"] for e in events if e["type"] == "run.step"]
    assert steps[0]["call_id"] == terminal[0]["id"] == steps[1]["call_id"]
    assert steps[-1]["cached"] is True


@pytest.mark.parametrize("kind", ["denied", "cancelled", "failed", "invalid"])
async def test_terminal_event_on_every_exit(tool_context, monkeypatch, kind):
    ctx, events, persisted = tool_context

    async def impl(bound, args):
        if kind == "cancelled":
            raise asyncio.CancelledError
        raise RuntimeError("SYNTHETIC hidden trace")

    register(monkeypatch, impl)
    if kind == "denied":
        monkeypatch.setattr(
            invoke_module,
            "check",
            AsyncMock(side_effect=ToolError("POLICY_DENIED", "SYNTHETIC hidden locator")),
        )
    args = {} if kind == "invalid" else {"query": "SYNTHETIC private"}
    if kind == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await invoke_module.invoke(ctx, "synthetic_tool", args)
    else:
        assert not (await invoke_module.invoke(ctx, "synthetic_tool", args)).ok
    activity = [e["data"] for e in events if e["type"] == "activity.updated"]
    assert activity[-1]["status"] == ("failed" if kind == "invalid" else kind)
    assert persisted.await_count == 1
    assert "SYNTHETIC hidden" not in json.dumps(events)
    assert "SYNTHETIC private" not in json.dumps(events)


async def test_shared_budget_consumed_for_cached_calls(tool_context, monkeypatch):
    ctx, events, _ = tool_context
    count = 0

    class Budget:
        def consume_tool(self):
            nonlocal count
            count += 1
            if count > 1:
                raise ToolError("BUDGET_EXCEEDED", "SYNTHETIC exhausted")

        def remaining_seconds(self):
            return 10.0

    async def impl(bound, args):
        return Output(evidence_id=uuid4(), evidence_code="E-0042")

    register(monkeypatch, impl)
    ctx.execution_budget = Budget()
    assert (await invoke_module.invoke(ctx, "synthetic_tool", {"query": "SYNTHETIC"})).ok
    denied = await invoke_module.invoke(ctx, "synthetic_tool", {"query": "SYNTHETIC"})
    assert not denied.ok
    assert denied.error["code"] == "BUDGET_EXCEEDED"
    assert count == 2


@pytest.mark.parametrize("commit_fails", [False, True])
async def test_capture_phases_follow_real_commit(tool_context, monkeypatch, commit_fails):
    ctx, events, _ = tool_context
    ctx = replace(ctx, parent_call_id=uuid4())
    ordering = []
    evidence = SimpleNamespace(
        id=uuid4(),
        code="E-0042",
        status="READY",
        source_class="SYNTHETIC",
        captured_at=datetime.now(UTC),
    )

    async def emit(event):
        events.append(event)
        if event["type"] == "activity.updated":
            ordering.append(event["data"]["phase"])

    async def commit():
        ordering.append("commit")
        if commit_fails:
            raise RuntimeError("SYNTHETIC database failure")

    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(commit=commit)

    async def fetch():
        ordering.append("fetch")
        return Fetched(
            b"SYNTHETIC private page",
            "text/plain",
            "https://example.org",
            200,
            {},
            datetime.now(UTC),
        )

    async def ingest(*args, **kwargs):
        ordering.append("ingest")
        return SimpleNamespace(evidence=evidence, duplicate=False)

    ctx.emit, ctx.session_factory = emit, factory
    monkeypatch.setattr(gate, "check", AsyncMock(return_value=object()))
    monkeypatch.setattr(gate, "record", AsyncMock())
    service = importlib.import_module("darknetra.evidence.service")
    monkeypatch.setattr(service, "ingest_bytes", ingest)
    monkeypatch.setattr(service, "get_text", AsyncMock(return_value=("SYNTHETIC excerpt", None)))
    spec = invoke_module.REGISTRY["fetch_page"]
    if commit_fails:
        with pytest.raises(RuntimeError):
            await gate.capture(ctx, spec=spec, locator="https://example.org", fetch=fetch)
    else:
        await gate.capture(ctx, spec=spec, locator="https://example.org", fetch=fetch)
    assert ordering[:5] == ["fetching", "fetch", "persisting", "ingest", "commit"]
    assert ("captured" in ordering) is (not commit_fails)
    activity = [e["data"] for e in events if e["type"] == "activity.updated"]
    assert all(e["id"] == str(ctx.parent_call_id) for e in activity)
    assert all(e["parent_id"] == str(ctx.agent_id) for e in activity)
    assert "https://example.org" not in json.dumps(events)
    assert "SYNTHETIC private page" not in json.dumps(events)


async def test_sdk_bridge_labels_actual_transport(tool_context, monkeypatch):
    from darknetra.agent.context import current_run_ctx
    from darknetra.tools.adapters import sdk_mcp

    ctx, _, _ = tool_context
    handlers = {}

    def tool(name, description, schema):
        def decorate(handler):
            handlers[name] = handler
            return handler

        return decorate

    invoked = AsyncMock(return_value=ToolResult(ok=True, data={}))
    monkeypatch.setattr(sdk_mcp, "tool", tool)
    monkeypatch.setattr(sdk_mcp, "create_sdk_mcp_server", lambda **kwargs: kwargs)
    monkeypatch.setattr(sdk_mcp, "invoke", invoked)
    token = current_run_ctx.set(ctx)
    try:
        sdk_mcp.build_sdk_server(AgentRole.CASE_LEAD)
        await handlers["robin_search"]({"query": "SYNTHETIC"})
    finally:
        current_run_ctx.reset(token)
    assert invoked.call_args.args[0].transport == "sdk_mcp"
    assert ctx.transport == "internal"


def test_robin_metadata_does_not_invent_remote_mcp():
    from darknetra.tools.presentation import tool_metadata

    assert tool_metadata(invoke_module.REGISTRY["robin_search"]) == {
        "display_name": "Robin search",
        "integration_id": "robin",
        "adapter_kind": "local_adapter",
    }


async def test_capture_evidence_survives_later_tool_failure(tool_context, monkeypatch):
    from darknetra.tools.presentation import emit_tool_activity

    ctx, events, _ = tool_context
    evidence = uuid4()

    async def impl(bound, args):
        await emit_tool_activity(
            bound,
            spec,
            bound.parent_call_id,
            status="running",
            phase="captured",
            ids=[evidence],
            codes=["E-0042"],
        )
        raise RuntimeError("SYNTHETIC parsing failure after commit")

    spec = register(monkeypatch, impl)
    await invoke_module.invoke(ctx, "synthetic_tool", {"query": "SYNTHETIC"})
    activity = [e["data"] for e in events if e["type"] == "activity.updated"]
    assert activity[-1]["status"] == "failed"
    assert activity[-1]["evidence_ids"] == [str(evidence)]
    assert activity[-1]["evidence_codes"] == ["E-0042"]
