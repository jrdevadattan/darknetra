from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import (
    ActorRef,
    EvidenceRef,
    FindingRef,
    Harness,
    MessageRole,
    RunStatus,
    Schema,
    ThreadStatus,
)


class ThreadCreate(Schema):
    title: str = Field(min_length=1, max_length=300)
    goal: str | None = None
    harness: Literal["CLAUDE", "NIM", "OFFLINE"] | None = None
    budget_usd: float = Field(2.0, gt=0, le=1000)


class ThreadPatch(Schema):
    title: str | None = Field(None, min_length=1, max_length=300)
    goal: str | None = None
    budget_usd: float | None = Field(None, gt=0, le=1000)
    status: ThreadStatus | None = None
    assignee_id: UUID | None = None


class Thread(Schema):
    id: UUID
    case_id: UUID
    title: str = Field(min_length=1, max_length=300)
    goal: str | None = None
    status: ThreadStatus
    harness: Harness
    summary: str | None = None
    pinned_findings: list[FindingRef]
    budget_usd: float = Field(2.0, gt=0, le=1000)
    spent_usd: float
    assignee: ActorRef | None = None
    created_by: ActorRef
    created_at: datetime
    last_message_at: datetime | None = None
    active_run_id: UUID | None = None


class Claim(Schema):
    text: str
    evidence_codes: list[str]
    kind: Literal["observed", "model", "candidate", "confirmed"]
    verified: bool
    reason: str | None = None


class Verification(Schema):
    ok: bool
    unverified_count: int
    revised: bool


class MessageBlock(Schema):
    type: Literal["text", "step", "attachment"]
    text: str | None = None
    tool: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Message(Schema):
    id: UUID
    thread_id: UUID
    run_id: UUID | None = None
    role: MessageRole
    blocks: list[MessageBlock]
    claims: list[Claim]
    verification: Verification | None = None
    cost_usd: float | None = None
    harness: str | None = None
    replayed_from_run_id: UUID | None = None
    at: datetime


class MessageCreate(Schema):
    content: str = Field(min_length=1, max_length=32000)
    attachments: list[str] = Field(default_factory=list)


class RunRef(Schema):
    run_id: UUID
    thread_id: UUID
    status: RunStatus


class ToolCall(Schema):
    id: UUID
    seq: int
    tool: str
    args: dict[str, Any]
    status: str
    policy_decision: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    evidence: list[EvidenceRef]
    error: dict[str, Any] | None = None


class Run(Schema):
    id: UUID
    thread_id: UUID
    status: RunStatus
    harness: Harness
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cost_usd: float
    error: dict[str, Any] | None = None
    tool_calls: list[ToolCall]
    replayed_from_run_id: UUID | None = None


class PinRequest(Schema):
    finding_id: UUID
    pinned: bool


class RunStarted(Schema):
    run_id: UUID
    thread_id: UUID
    harness: Harness
    budget_usd: float = Field(2.0, gt=0, le=1000)
    replayed: bool


class RunStep(Schema):
    seq: int
    kind: Literal["tool_call", "subagent"]
    tool: str
    agent: str | None = None
    status: Literal["started", "finished", "denied", "error"]
    summary: str
    evidence_codes: list[str]
    duration_ms: int | None = None
    error: dict[str, Any] | None = None
    call_id: UUID | None = None
    parent_id: UUID | None = None
    cached: bool = False
    evidence_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class MessageDelta(Schema):
    text: str


class MessageCompleted(Schema):
    message: Message


class StoreChanged(Schema):
    kind: Literal[
        "evidence", "observation", "link", "edge", "alert", "finding", "wallet", "trend", "chunk"
    ]
    ids: list[UUID]


class RunFinished(Schema):
    status: RunStatus
    cost_usd: float
    tokens_in: int
    tokens_out: int
    cost_complete: bool = True


class RunError(Schema):
    code: str
    message: str


class RunCancelled(Schema):
    pass
