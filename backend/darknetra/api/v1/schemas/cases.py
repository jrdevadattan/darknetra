from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from .common import ActorRef, CaseRole, CaseStatus, ResourceRef, Schema, SourceClass


class SourcePolicy(Schema):
    allowed_source_classes: list[SourceClass] = [
        "SYNTHETIC",
        "SEIZED",
        "UPLOAD",
        "OSINT_SURFACE",
        "CHAIN",
        "REPORT",
    ]
    tor_enabled: bool = False
    person_lookup_enabled: bool = False
    telegram_enabled: bool = False
    max_requests_per_hour: dict[
        Literal["surface", "dark", "chain", "identity", "telegram"], Annotated[int, Field(ge=0)]
    ] = {
        "surface": 60,
        "dark": 12,
        "chain": 120,
        "identity": 20,
        "telegram": 30,
    }
    retention_days: int | None = Field(None, gt=0)
    enabled_plugins: list[str] | None = Field(None, max_length=64)

    @field_validator("enabled_plugins")
    @classmethod
    def reviewed_plugins(cls, values):
        if values is not None:
            from darknetra.plugins.catalog import catalog

            if any(name not in catalog() for name in values):
                raise ValueError("Only reviewed plugin IDs are allowed")
            return sorted(set(values))
        return values


class CaseCreate(Schema):
    title: str = Field(min_length=1, max_length=300)
    scope_notes: str | None = None
    authority_ref: str | None = None
    source_policy: SourcePolicy | None = None
    demo: bool = False


class CasePatch(Schema):
    title: str | None = Field(None, min_length=1, max_length=300)
    scope_notes: str | None = None
    authority_ref: str | None = None
    source_policy: SourcePolicy | None = None
    legal_hold: bool | None = None


class Case(Schema):
    id: UUID
    code: str
    title: str = Field(min_length=1, max_length=300)
    status: CaseStatus
    scope_notes: str | None = None
    authority_ref_present: bool
    source_policy: SourcePolicy
    legal_hold: bool
    demo: bool
    created_by: ActorRef
    opened_at: datetime
    closed_at: datetime | None = None
    my_role: CaseRole | None = None


class CaseSummary(Schema):
    evidence_by_class: dict[str, int]
    evidence_by_status: dict[str, int]
    observations_by_type: dict[str, int]
    pending_candidates: int
    open_alerts: int
    active_items: int
    threads: int
    last_activity_at: datetime | None = None


class TimelineEntry(Schema):
    at: datetime
    kind: str
    title: str = Field(min_length=1, max_length=300)
    ref: ResourceRef
    actor: ActorRef | None = None


class MemberCreate(Schema):
    user_id: UUID
    role: CaseRole


class MemberPatch(Schema):
    role: CaseRole


class CaseMember(Schema):
    user: ActorRef
    role: CaseRole
    added_at: datetime


class LedgerImportResult(Schema):
    nodes: int
    edges: int
    addresses: int
