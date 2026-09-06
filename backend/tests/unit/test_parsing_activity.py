"""SYNTHETIC source parsing reports progress only after successful capture."""

import importlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from darknetra.auth.actor import Actor
from darknetra.capture.fetcher import Fetched
from darknetra.capture.gate import CaptureResult
from darknetra.tools.contracts import ToolContext, ToolError


@pytest.mark.parametrize("name", ["robin_search", "surface_search", "rss_read", "public_page_read"])
@pytest.mark.parametrize("outcome", ["captured", "quarantined", "denied", "missing_bytes"])
async def test_parsing_activity_follows_capture_and_retains_references(monkeypatch, name, outcome):
    module = importlib.import_module(
        "darknetra.tools.impl.robin" if name == "robin_search" else "darknetra.tools.impl.research"
    )
    order, activity = [], []
    result = CaptureResult(
        evidence_code="E-0042",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="SYNTHETIC",
        source_class="SYNTHETIC",
        captured_at=datetime.now(UTC),
        quarantined=outcome == "quarantined",
    )

    async def emit(event):
        activity.append(event["data"])
        order.append(event["data"]["phase"])

    ctx = ToolContext(
        uuid4(),
        Actor("MODEL", None),
        None,
        None,
        run_id=uuid4(),
        agent_id=uuid4(),
        parent_call_id=uuid4(),
        emit=emit,
    )

    async def fetch(self, url):
        order.append("fetch")
        return Fetched(b"SYNTHETIC source", "text/html", url, 200, {}, datetime.now(UTC))

    async def capture(bound, **kwargs):
        if outcome == "denied":
            raise ToolError("POLICY_DENIED", "SYNTHETIC denied")
        if outcome != "missing_bytes":
            await kwargs["fetch"]()
        order.append("commit")
        return result

    def parse(*args, **kwargs):
        assert order == ["fetch", "commit", "parsing"]
        order.append("parse")
        if name == "robin_search":
            return []
        if name == "public_page_read":
            return "SYNTHETIC"
        return (
            module.SurfaceSearchOutput(capture=result, provider="duckduckgo")
            if name == "surface_search"
            else module.RssReadOutput(capture=result)
        )

    monkeypatch.setattr(module.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(module, "capture", capture)
    parse_name = {
        "robin_search": "parse_index",
        "surface_search": "parse_search",
        "rss_read": "parse_feed",
        "public_page_read": "extract_public_text",
    }[name]
    monkeypatch.setattr(module, parse_name, parse)
    input_name = {
        "robin_search": "RobinSearchInput",
        "surface_search": "SurfaceSearchInput",
        "rss_read": "RssReadInput",
        "public_page_read": "PublicPageInput",
    }[name]
    args = getattr(module, input_name)(
        **({"query": "SYNTHETIC"} if "search" in name else {"url": "https://example.org"})
    )
    if outcome in {"denied", "missing_bytes"}:
        with pytest.raises(ToolError):
            await getattr(module, name)(ctx, args)
    else:
        await getattr(module, name)(ctx, args)
    if outcome == "captured":
        assert order == ["fetch", "commit", "parsing", "parse"]
        assert activity[0]["id"] == str(ctx.parent_call_id)
        assert activity[0]["parent_id"] == str(ctx.agent_id)
        assert activity[0]["evidence_ids"] == [str(result.evidence_id)]
        assert activity[0]["evidence_codes"] == [result.evidence_code]
        assert activity[0]["summary"] == "Parsing captured source"
    else:
        assert activity == []


def test_stdio_truncated_result_schema_accepts_evidence_codes():
    from jsonschema import validate

    from darknetra.tools.adapters.stdio_mcp import output_schema
    from darknetra.tools.contracts import ToolResult
    from darknetra.tools.registry import REGISTRY

    result = ToolResult(
        ok=True,
        truncated=True,
        data={
            "notice": "SYNTHETIC truncated result",
            "evidence_ids": [str(uuid4())],
            "evidence_codes": ["E-0042"],
        },
    )
    validate(result.model_dump(mode="json"), output_schema(REGISTRY["read_evidence"]))
