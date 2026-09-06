from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Schema, SourceClass


class ToolHealth(Schema):
    status: Literal["ok", "degraded", "failed", "unknown", "disabled_by_mode"]
    checked_at: datetime | None = None
    latency_ms: int | None = None
    message: str | None = None


class ToolInfo(Schema):
    name: str = Field(min_length=1, max_length=200)
    display_name: str | None = None
    integration_id: str | None = None
    adapter_kind: Literal["internal", "http_api", "local_adapter"] | None = None
    description: str | None = None
    allowed_roles: list[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    invocation_transports: list[str] = Field(default_factory=list)
    kind: Literal["INTERNAL", "MCP", "API", "CLI"]
    server: str | None = None
    lane: str
    requires_network: bool
    source_class: SourceClass | None = None
    policy_tags: list[str]
    rate_cap_per_hour: int | None = None
    enabled: bool
    health: ToolHealth
