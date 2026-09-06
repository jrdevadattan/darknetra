from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas.common import Page
from darknetra.api.v1.schemas.tools import ToolHealth, ToolInfo
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.authz.deps import current_actor, require
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.errors import NotFound
from darknetra.tools.presentation import tool_metadata
from darknetra.tools.registry import REGISTRY

router = APIRouter(tags=["tools"])


def info(name, settings):
    spec = REGISTRY[name]
    status = (
        "disabled_by_mode"
        if spec.requires_network and settings.offline_mode
        else (
            "failed" if spec.unavailable_reason else ("unknown" if spec.requires_network else "ok")
        )
    )
    return ToolInfo(
        name=name,
        **tool_metadata(spec),
        description=spec.description,
        allowed_roles=sorted(spec.allowed_for),
        input_schema=spec.input_model.model_json_schema(),
        output_schema=spec.output_model.model_json_schema(),
        invocation_transports=["internal", "sdk_mcp", "stdio_mcp"],
        kind="API" if spec.requires_network else "INTERNAL",
        lane=spec.lane.value,
        requires_network=spec.requires_network,
        source_class=spec.source_class,
        policy_tags=sorted(spec.policy_tags),
        enabled=not bool(spec.unavailable_reason),
        health=ToolHealth(
            status=status,
            message=spec.unavailable_reason
            or (
                "Not probed; a lookup requires case capture policy"
                if spec.requires_network
                else None
            ),
        ),
    )


@router.get("/tools", response_model=Page[ToolInfo])
async def list_tools(request: Request, actor: Actor = Depends(current_actor)):
    return Page(items=[info(name, request.app.state.settings) for name in REGISTRY])


@router.post("/tools/{name}/health", response_model=ToolHealth)
async def health(
    name: str,
    request: Request,
    actor: Actor = Depends(require(Permission.TOOLS_HEALTH)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if name not in REGISTRY:
        raise NotFound("Resource not found")
    await record(db, actor=actor, action="tool.health", detail={"tool": name})
    return info(name, request.app.state.settings).health
