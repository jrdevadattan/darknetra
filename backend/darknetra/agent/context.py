from contextvars import ContextVar

from darknetra.tools.contracts import ToolContext

current_run_ctx: ContextVar[ToolContext] = ContextVar("darknetra_tool_context")
