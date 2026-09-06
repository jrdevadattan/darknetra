from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from .common import ActorRef, EvidenceRef, ItemType, Schema


class WatchlistCreate(Schema):
    name: str = Field(min_length=1, max_length=200)


class Watchlist(Schema):
    id: UUID
    case_id: UUID
    name: str = Field(min_length=1, max_length=200)
    active: bool
    created_by: ActorRef
    created_at: datetime


class WatchlistItemIn(Schema):
    type: ItemType
    value: str
    variants: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    interval_seconds: int = Field(21600, ge=60)
    active: bool = True
    note: str | None = None


class WatchlistItemPatch(Schema):
    value: str | None = None
    variants: list[str] | None = None
    sources: list[str] | None = None
    interval_seconds: int | None = Field(None, ge=60)
    active: bool | None = None
    note: str | None = None


class WatchlistItem(WatchlistItemIn):
    id: UUID
    watchlist_id: UUID
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    state: dict[str, Any]


class MonitorRun(Schema):
    id: UUID
    item_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    sources_run: dict[str, Any]
    new_hits: int
    errors: dict[str, Any]


class MonitorHit(Schema):
    id: UUID
    item_id: UUID
    evidence: EvidenceRef | None = None
    url_display: str | None = None
    relevance: float
    alertable: bool
    reasons: list[str]
    alert_id: UUID | None = None
    at: datetime
