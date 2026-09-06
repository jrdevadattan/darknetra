"""NVIDIA NIM adapter using its OpenAI-compatible chat-completions API."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx

from darknetra.agent.harness_base import system_prompt
from darknetra.tools.contracts import AgentRole, ToolContext, ToolError, ToolSpec
from darknetra.tools.invoke import invoke
from darknetra.tools.registry import for_role


def _openai_tools(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_model.model_json_schema(),
            },
        }
        for spec in specs
    ]


def _usage_event(ctx: ToolContext, usage: dict[str, Any]) -> dict[str, Any]:
    valid = isinstance(usage, dict) and all(
        type(usage.get(key)) is int and usage[key] >= 0
        for key in ("prompt_tokens", "completion_tokens")
    )
    tokens_in = usage["prompt_tokens"] if valid else 0
    tokens_out = usage["completion_tokens"] if valid else 0
    input_rate = ctx.settings.nim_input_cost_per_million
    output_rate = ctx.settings.nim_output_cost_per_million
    complete = valid and input_rate is not None and output_rate is not None
    cost = None
    if complete:
        cost = float(
            (
                Decimal(tokens_in) * Decimal(str(input_rate))
                + Decimal(tokens_out) * Decimal(str(output_rate))
            )
            / Decimal(1_000_000)
        )
    return {
        "type": "usage",
        "cost_usd": cost,
        "cost_complete": complete,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


class NimHarness:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def run(
        self,
        ctx: ToolContext,
        prompt: str,
        *,
        goal: str | None = None,
        history: list[dict[str, Any]] | None = None,
        budget: float = 2.0,
    ) -> AsyncIterator[dict[str, Any]]:
        settings = ctx.settings
        if not settings.nim_base_url or not settings.nim_model:
            raise ToolError("UNAVAILABLE", "NVIDIA NIM endpoint and model are not configured")
        if (
            settings.nim_input_cost_per_million is None
            or settings.nim_output_cost_per_million is None
        ):
            raise ToolError(
                "UNAVAILABLE",
                "Configure NIM token rates to enforce the USD budget; use explicit zero rates only for a free deployment",
            )
        model = (
            settings.nim_worker_model or settings.nim_model
            if ctx.role != AgentRole.CASE_LEAD
            else settings.nim_model
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(goal, ctx.role)},
            *[
                {"role": item["role"], "content": item["content"]}
                for item in (history or [])[-20:]
                if item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str)
            ],
            {"role": "user", "content": prompt},
        ]
        specs = [s for s in for_role(ctx.role) if s.name not in ctx.disabled_tools]
        names = {spec.name for spec in specs}
        headers = {"Content-Type": "application/json"}
        if settings.nim_api_key:
            headers["Authorization"] = f"Bearer {settings.nim_api_key.get_secret_value()}"
        turns = 16 if ctx.role == AgentRole.CASE_LEAD else 8
        endpoint = settings.nim_base_url.rstrip("/") + "/chat/completions"
        spent = Decimal("0")
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=settings.nim_timeout_seconds,
                headers=headers,
            ) as client:
                for _ in range(turns):
                    request_data = {
                        "model": model,
                        "messages": messages,
                        "tools": _openai_tools(specs),
                        "tool_choice": "auto",
                        "max_tokens": settings.nim_max_tokens,
                    }
                    encoded = json.dumps(request_data).encode()
                    if len(encoded) > 512_000:
                        raise ToolError("BUDGET_EXCEEDED", "NIM context size limit reached")
                    reserve = (
                        (len(encoded) + 4096) * settings.nim_input_cost_per_million
                        + settings.nim_max_tokens * settings.nim_output_cost_per_million
                    ) / 1_000_000
                    if spent + Decimal(str(reserve)) > Decimal(str(budget)):
                        raise ToolError(
                            "BUDGET_EXCEEDED", "NIM remaining budget cannot cover the next request"
                        )
                    async with client.stream("POST", endpoint, json=request_data) as response:
                        response.raise_for_status()
                        body = bytearray()
                        async for block in response.aiter_bytes():
                            body.extend(block)
                            if len(body) > 2_000_000:
                                raise ToolError(
                                    "UNAVAILABLE", "NIM response exceeds the size limit"
                                )
                    payload = json.loads(body)
                    choices = payload.get("choices") or []
                    if not choices or not isinstance(choices[0].get("message"), dict):
                        raise ToolError("UNAVAILABLE", "NVIDIA NIM returned an invalid response")
                    usage = _usage_event(ctx, payload.get("usage") or {})
                    yield usage
                    if not usage["cost_complete"]:
                        raise ToolError("UNAVAILABLE", "NIM did not report valid token usage")
                    if usage["cost_usd"] is not None:
                        spent += Decimal(str(usage["cost_usd"]))
                        if spent > Decimal(str(budget)):
                            raise ToolError("BUDGET_EXCEEDED", "NVIDIA NIM run budget exhausted")
                    message = choices[0]["message"]
                    assistant_message = {
                        "role": "assistant",
                        "content": message.get("content"),
                    }
                    if message.get("tool_calls"):
                        assistant_message["tool_calls"] = message["tool_calls"]
                    messages.append(assistant_message)
                    content = message.get("content")
                    if isinstance(content, str) and content:
                        yield {"type": "assistant", "text": content}
                    tool_calls = message.get("tool_calls") or []
                    if not isinstance(tool_calls, list) or len(tool_calls) > 16:
                        raise ToolError("UNAVAILABLE", "NIM tool call limit exceeded")
                    if not tool_calls:
                        return
                    for call in tool_calls:
                        call_id = str(call.get("id", ""))
                        function = call.get("function") or {}
                        if len(str(function.get("arguments", ""))) > 32000:
                            raise ToolError(
                                "VALIDATION", "NIM tool arguments exceed the size limit"
                            )
                        name = function.get("name")
                        try:
                            arguments = json.loads(function.get("arguments") or "{}")
                            if not isinstance(arguments, dict):
                                raise ValueError
                        except (TypeError, ValueError, json.JSONDecodeError):
                            result = {
                                "ok": False,
                                "error": {
                                    "code": "VALIDATION",
                                    "message": "Tool arguments are invalid JSON",
                                },
                            }
                        else:
                            if name not in names:
                                result = {
                                    "ok": False,
                                    "error": {
                                        "code": "POLICY_DENIED",
                                        "message": "Tool is not available to this agent role",
                                    },
                                }
                            else:
                                invoked = await invoke(ctx, str(name), arguments)
                                result = invoked.model_dump(mode="json")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(result, separators=(",", ":")),
                            }
                        )
            raise ToolError("UNAVAILABLE", "NVIDIA NIM tool turn limit reached")
        except ToolError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise ToolError("UNAVAILABLE", "NVIDIA NIM is unavailable") from None
