"""Provider-independent public activity contract; never private model reasoning."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .common import RunStatus, Schema


class ActivityUpdate(Schema):
    schema_version: Literal[1] = 1
    id: UUID
    parent_id: UUID | None = None
    kind: Literal["agent", "tool", "stage"]
    label: str = Field(max_length=200)
    display_name: str | None = None
    adapter_kind: Literal["internal", "http_api", "local_adapter"] | None = None
    status: Literal[
        "queued", "running", "completed", "failed", "denied", "cancelled", "interrupted"
    ]
    phase: str = Field("working", max_length=80)
    summary: str = Field("", max_length=500)
    agent_role: str | None = None
    tool_name: str | None = None
    integration_id: str | None = None
    transport: str | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=200)
    evidence_codes: list[str] = Field(default_factory=list, max_length=200)
    duration_ms: int | None = Field(None, ge=0)
    error_code: str | None = None
    cached: bool = False
    seq: int = Field(0, ge=0)
    at: datetime | None = None


class ActivityNode(ActivityUpdate):
    terminal_inferred: bool = False


class ActivityEdge(Schema):
    source: UUID
    target: UUID


class ExecutionSnapshot(Schema):
    schema_version: Literal[1] = 1
    case_id: UUID
    thread_id: UUID
    run_id: UUID
    run_status: RunStatus
    cost_usd: float = 0
    cost_complete: bool | None = None
    cursor: int
    nodes: list[ActivityNode]
    edges: list[ActivityEdge]
    events: list[ActivityUpdate]
    truncated: bool = False
    replayed_from_run_id: UUID | None = None
    summary_policy: Literal["public_operational_status_only"] = "public_operational_status_only"
