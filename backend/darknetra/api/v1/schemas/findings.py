from datetime import datetime
from uuid import UUID

from pydantic import Field

from .common import (
    ActorRef,
    DecisionTarget,
    DecisionValue,
    EvidenceRef,
    FindingKind,
    FindingStatus,
    Schema,
)


class DecisionCreate(Schema):
    target_type: DecisionTarget
    target_id: UUID
    decision: DecisionValue
    rationale: str = Field(min_length=1, max_length=10000)
    supersede: bool = False


class Decision(Schema):
    id: UUID
    target_type: DecisionTarget
    target_id: UUID
    decision: DecisionValue
    rationale: str = Field(min_length=1, max_length=10000)
    decided_by: ActorRef
    at: datetime
    superseded_by: UUID | None = None


class FindingCreate(Schema):
    title: str = Field(min_length=1, max_length=300)
    claim: str
    evidence_codes: list[str]
    method: str
    method_version: str | None = None
    kind_hint: str | None = None
    thread_id: UUID | None = None
    source_message_id: UUID | None = None
    claim_index: int | None = None


class Finding(Schema):
    id: UUID
    case_id: UUID
    thread_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    claim: str
    kind: FindingKind
    evidence: list[EvidenceRef]
    method: str
    method_version: str | None = None
    confidence: float | None = None
    status: FindingStatus
    version: int
    supersedes_id: UUID | None = None
    created_by: ActorRef
    at: datetime
    decision: Decision | None = None


class PromoteRequest(Schema):
    decision_id: UUID
