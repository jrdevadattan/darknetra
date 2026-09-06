"""Tool-free transports; never import case tools, context, or claim verification."""

import json
from decimal import Decimal

import httpx

from darknetra.errors import BudgetExceeded, PolicyDenied, Unavailable


def normal_chat_prompt():
    return "You are a general private chat assistant. You have no access to cases, evidence, investigation tools, plugins, files, or external browsing. Do not claim hidden access or confirm investigative findings. Respond naturally to the user."


async def select_provider(provider, settings):
    if provider not in {"AUTO", "CLAUDE", "NIM", "OFFLINE", "DETERMINISTIC"}:
        raise Unavailable("Unknown private chat provider")
    if provider == "AUTO":
        if settings.harness_mode == "nim":
            return await select_provider("NIM", settings)
        if not settings.offline_mode and settings.anthropic_api_key:
            return "CLAUDE"
        if not settings.offline_mode and settings.nim_base_url and settings.nim_model:
            return "NIM"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(settings.ollama_url.rstrip("/") + "/api/tags")
                response.raise_for_status()
                if any(
                    m.get("name") == settings.offline_model
                    for m in response.json().get("models", [])
                ):
                    return "OFFLINE"
        except (httpx.HTTPError, ValueError):
            pass
        raise Unavailable("No private chat provider is ready")
    if provider == "DETERMINISTIC":
        raise Unavailable("Deterministic case quotation mode is unavailable for private chats")
    if provider == "CLAUDE" and (settings.offline_mode or not settings.anthropic_api_key):
        raise Unavailable("Claude is unavailable")
    if provider == "NIM" and (
        settings.offline_mode or not (settings.nim_base_url and settings.nim_model)
    ):
        raise Unavailable("NIM is unavailable")
    return provider


def token_count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Unavailable("Provider returned invalid usage")
    return value


async def generate(provider, settings, history, budget):
    if provider not in {"CLAUDE", "NIM", "OFFLINE"}:
        raise Unavailable("Private chat provider is not resolved or supported")
    messages = [{"role": "system", "content": normal_chat_prompt()}, *history]
    if provider == "CLAUDE":
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            tools=[],
            allowed_tools=[],
            disallowed_tools=[
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "WebFetch",
                "WebSearch",
                "NotebookEdit",
                "Agent",
                "Task",
            ],
            mcp_servers={},
            strict_mcp_config=True,
            skills=[],
            plugins=[],
            setting_sources=[],
            system_prompt=normal_chat_prompt(),
            model=settings.worker_model,
            max_turns=1,
            max_budget_usd=float(budget),
            permission_mode="dontAsk",
            env={"ANTHROPIC_API_KEY": settings.anthropic_api_key.get_secret_value()},
        )
        received_result = False
        async for message in query(prompt=json.dumps(history), options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if block.__class__.__name__ == "ToolUseBlock":
                        raise PolicyDenied("Private chat provider attempted a tool call")
                    if isinstance(block, TextBlock):
                        yield {"type": "assistant", "text": block.text}
            elif isinstance(message, ResultMessage):
                received_result = True
                usage = message.usage or {}
                cost = Decimal(str(message.total_cost_usd or 0))
                if not cost.is_finite() or cost < 0:
                    raise Unavailable("Provider returned invalid usage")
                yield {
                    "type": "usage",
                    "tokens_in": token_count(usage.get("input_tokens")),
                    "tokens_out": token_count(usage.get("output_tokens")),
                    "cost_usd": cost,
                    "cost_complete": message.total_cost_usd is not None,
                }
                if message.is_error:
                    raise Unavailable("Claude could not complete this run")
        if not received_result:
            raise Unavailable("Claude disconnected before final usage")
        return
    if provider == "NIM":
        rates = (settings.nim_input_cost_per_million, settings.nim_output_cost_per_million)
        if any(r is None or not Decimal(str(r)).is_finite() or r < 0 for r in rates):
            raise Unavailable("NIM pricing must be configured for private chat USD budgets")
        input_rate, output_rate = (Decimal(str(r)) for r in rates)
        # UTF-8 byte count is a conservative input-token reservation, with framing headroom.
        reserved = Decimal(len(json.dumps(messages).encode("utf-8")) + 1024) * input_rate / 1000000
        remaining = budget - reserved
        if remaining <= 0:
            raise BudgetExceeded("Remaining budget cannot cover the private chat context")
        max_tokens = settings.nim_max_tokens
        if output_rate:
            max_tokens = min(max_tokens, int(remaining * 1000000 / output_rate))
        if max_tokens < 1:
            raise BudgetExceeded("Remaining budget cannot cover private chat output")
        url = settings.nim_base_url.rstrip("/") + "/chat/completions"
        headers = (
            {"Authorization": "Bearer " + settings.nim_api_key.get_secret_value()}
            if settings.nim_api_key
            else {}
        )
        body = {
            "model": settings.nim_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
    else:
        url = settings.ollama_url.rstrip("/") + "/api/chat"
        headers = {}
        body = {
            "model": settings.offline_model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": settings.nim_max_tokens},
        }
    async with httpx.AsyncClient(timeout=settings.nim_timeout_seconds) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 1024 * 1024:
                    raise Unavailable("Provider response exceeded the private chat limit")
            data = json.loads(raw)
    message = data["choices"][0]["message"] if provider == "NIM" else data["message"]
    if message.get("tool_calls") or message.get("function_call"):
        raise PolicyDenied("Private chat provider attempted a tool call")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip() or len(content) > 65536:
        raise Unavailable("Provider returned no assistant answer")
    yield {"type": "assistant", "text": content}
    usage = data.get("usage", {}) if provider == "NIM" else data
    ti = token_count(usage.get("prompt_tokens" if provider == "NIM" else "prompt_eval_count"))
    to = token_count(usage.get("completion_tokens" if provider == "NIM" else "eval_count"))
    rates = (settings.nim_input_cost_per_million, settings.nim_output_cost_per_million)
    complete = provider == "OFFLINE" or (all(r is not None for r in rates) and bool(usage))
    cost = Decimal(0)
    if provider == "NIM" and complete:
        cost = (Decimal(str(rates[0])) * ti + Decimal(str(rates[1])) * to) / 1000000
    yield {
        "type": "usage",
        "tokens_in": ti,
        "tokens_out": to,
        "cost_usd": cost,
        "cost_complete": complete,
    }
