"""Ollama tool loop using the same invocation and citation boundary."""

from collections.abc import AsyncIterator
from typing import Any

from ollama import AsyncClient

from darknetra.agent.harness_base import system_prompt
from darknetra.tools.adapters.ollama import to_ollama_tools
from darknetra.tools.contracts import Lane, ToolContext, ToolError
from darknetra.tools.invoke import invoke
from darknetra.tools.registry import for_role


class OllamaHarness:
    async def run(
        self,
        ctx: ToolContext,
        prompt: str,
        *,
        goal: str | None = None,
        history: list[dict[str, Any]] | None = None,
        budget: float = 2.0,
    ) -> AsyncIterator[dict[str, Any]]:
        client = AsyncClient(host=ctx.settings.ollama_url, timeout=120)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt(goal, ctx.role)},
            *(history or [])[-20:],
            {"role": "user", "content": prompt},
        ]
        specs = [
            spec
            for spec in for_role(ctx.role)
            if (spec.lane == Lane.EVIDENCE or spec.name == "delegate_task")
            and spec.name not in ctx.disabled_tools
        ]
        names = {spec.name for spec in specs}
        try:
            for _ in range(8):
                response = await client.chat(
                    model=ctx.settings.offline_model,
                    messages=messages,
                    tools=to_ollama_tools(specs),
                )
                yield {
                    "type": "usage",
                    "cost_usd": 0,
                    "tokens_in": response.prompt_eval_count or 0,
                    "tokens_out": response.eval_count or 0,
                }
                message = response.message
                messages.append(message.model_dump(exclude_none=True))
                if message.content:
                    yield {"type": "assistant", "text": message.content}
                if not message.tool_calls:
                    return
                for call in message.tool_calls:
                    if call.function.name not in names:
                        content = '{"ok":false,"error":{"code":"POLICY_DENIED","message":"Tool unavailable offline"}}'
                    else:
                        result = await invoke(
                            ctx, call.function.name, dict(call.function.arguments)
                        )
                        content = result.model_dump_json()
                    messages.append(
                        {"role": "tool", "tool_name": call.function.name, "content": content}
                    )
            raise ToolError("UNAVAILABLE", "Offline model tool turn limit reached")
        except ToolError:
            raise
        except Exception:
            raise ToolError(
                "UNAVAILABLE", "Ollama or the configured offline model is unavailable"
            ) from None
