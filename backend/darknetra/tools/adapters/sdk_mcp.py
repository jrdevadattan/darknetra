from dataclasses import replace
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from darknetra.agent.context import current_run_ctx
from darknetra.tools.contracts import AgentRole, ToolSpec
from darknetra.tools.invoke import invoke
from darknetra.tools.registry import for_role


def build_sdk_server(role: AgentRole) -> McpSdkServerConfig:
    def build(spec: ToolSpec) -> Any:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            ctx = replace(current_run_ctx.get(), transport="sdk_mcp")
            result = await invoke(ctx, spec.name, args)
            return {
                "content": [{"type": "text", "text": result.model_dump_json()}],
                "isError": not result.ok,
            }

        return tool(spec.name, spec.description, spec.input_model.model_json_schema())(handler)

    return create_sdk_mcp_server(
        name="darknetra", version="0.1.0", tools=[build(spec) for spec in for_role(role)]
    )
