"""Registry entry point for bounded case-lead delegation."""

from pydantic import BaseModel

from darknetra.agent.delegation import (
    DelegateTaskInput as DelegateTaskInput,
)
from darknetra.agent.delegation import (
    DelegateTaskOutput as DelegateTaskOutput,
)
from darknetra.agent.delegation import (
    run_specialist,
)
from darknetra.tools.contracts import ToolContext


async def delegate_task(ctx: ToolContext, args: BaseModel) -> DelegateTaskOutput:
    request = DelegateTaskInput.model_validate(args)
    return await run_specialist(ctx, request)
