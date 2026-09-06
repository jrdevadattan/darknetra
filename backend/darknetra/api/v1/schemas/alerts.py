from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from .common import AlertKind, AlertStatus, EvidenceRef, FindingRef, Schema
from .findings import Decision, Finding


class Alert(Schema):
    id: UUID
    case_id: UUID
    kind: AlertKind
    title: str = Field(min_length=1, max_length=300)
    summary: str
    evidence: list[EvidenceRef]
    item_id: UUID | None = None
    diversity: dict[str, Any]
    config_version: str
    status: AlertStatus
    finding_id: UUID | None = None
    assigned_to: UUID | None = None
    at: datetime
    handled_at: datetime | None = None
    decision: Decision | None = None


class EvidenceChanges(Schema):
    count: int
    codes: list[str]


class Changes(Schema):
    since: datetime
    evidence: EvidenceChanges
    hits: int
    alerts: list[Alert]
    decisions: list[Decision]
    candidates_rescored: int
    findings: list[FindingRef]


class EscalateResult(Schema):
    alert: Alert
    finding: Finding
