"""Public operational metadata; never interpolate arguments or provider content."""

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from darknetra.tools.contracts import ToolContext, ToolSpec

if TYPE_CHECKING:
    from darknetra.capture.gate import CaptureResult

_INTEGRATIONS = {
    "robin_search": ("Robin search", "robin", "local_adapter"),
    "agent_reach_read": ("Agent Reach reader", "agent_reach", "local_adapter"),
    "public_page_read": ("Public page reader", "trafilatura", "local_adapter"),
    "rss_read": ("RSS feed reader", "feedparser", "local_adapter"),
    "surface_search": ("Surface search", "surface_search", "local_adapter"),
    "web_search": ("Web search", "duckduckgo", "http_api"),
    "fetch_page": ("Fetch public page", "public_web", "http_api"),
    "wayback_lookup": ("Wayback lookup", "wayback", "http_api"),
    "onion_search": ("Public onion index search", "ahmia", "http_api"),
    "keyserver_lookup": ("Public key lookup", "keyserver", "http_api"),
    "chain_lookup": ("Chain lookup", "chain", "http_api"),
    "delegate_task": ("Delegate to specialist", "darknetra", "internal"),
}

_SUMMARIES = {
    "authorizing": "Checking tool authorization",
    "executing": "Tool started",
    "fetching": "Fetching public source",
    "persisting": "Persisting captured evidence",
    "captured": "Captured evidence persisted",
    "parsing": "Parsing captured source",
    "complete": "Tool completed",
    "cache_hit": "Previously captured result reused",
    "error": "Tool unavailable or denied",
    "cancelled": "Tool cancelled",
}


def tool_metadata(spec: ToolSpec) -> dict[str, str]:
    display, integration, adapter = _INTEGRATIONS.get(
        spec.name, (spec.name.replace("_", " ").capitalize(), "darknetra", "internal")
    )
    return {"display_name": display, "integration_id": integration, "adapter_kind": adapter}


def evidence_codes(value: Any) -> list[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"evidence_code", "code"} and isinstance(item, str):
                if re.fullmatch(r"E-[0-9]+", item):
                    found.add(item)
            elif key == "evidence_codes" and isinstance(item, list):
                found.update(i for i in item if isinstance(i, str) and re.fullmatch(r"E-[0-9]+", i))
            found.update(evidence_codes(item))
    elif isinstance(value, list):
        for item in value:
            found.update(evidence_codes(item))
    return sorted(found)


async def emit_parsing(ctx: ToolContext, tool: str, capture_result: "CaptureResult") -> None:
    """Called only after capture returns and the adapter accepts its source bytes."""
    call_id = getattr(ctx, "parent_call_id", None)
    if call_id is None or capture_result.quarantined:
        return
    from darknetra.tools.registry import REGISTRY

    await emit_tool_activity(
        ctx,
        REGISTRY[tool],
        call_id,
        status="running",
        phase="parsing",
        ids=[capture_result.evidence_id],
        codes=[capture_result.evidence_code],
    )


async def emit_tool_activity(
    ctx: ToolContext,
    spec: ToolSpec | None,
    call_id: UUID,
    *,
    status: str,
    phase: str,
    ids: list[UUID] | None = None,
    codes: list[str] | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    cached: bool = False,
) -> dict[str, Any]:
    metadata = (
        tool_metadata(spec)
        if spec
        else {
            "display_name": "Unknown tool",
            "integration_id": "darknetra",
            "adapter_kind": "internal",
        }
    )
    parent = ctx.agent_id or ctx.run_id
    data: dict[str, Any] = {
        "id": str(call_id),
        "parent_id": str(parent) if parent else None,
        "kind": "tool",
        "label": metadata["display_name"],
        "status": status,
        "phase": phase,
        "tool_name": spec.name if spec else "unknown_tool",
        **metadata,
        "transport": ctx.transport,
        "agent_role": ctx.role.value,
        "summary": _SUMMARIES[phase],
        "evidence_ids": [str(i) for i in (ids or [])[:200]],
        "evidence_codes": (codes or [])[:200],
        "duration_ms": duration_ms,
        "error_code": error_code,
        "cached": cached,
    }
    await ctx.emit({"type": "activity.updated", "data": data})
    return data
