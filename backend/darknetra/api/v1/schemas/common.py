from typing import Any, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")


GlobalRole = Literal["ADMIN", "INVESTIGATOR", "VIEWER"]
CaseRole = Literal["OWNER", "LEAD", "ANALYST", "VIEWER"]
CaseStatus = Literal["OPEN", "CLOSED", "ARCHIVED"]
SourceClass = Literal[
    "SYNTHETIC", "SEIZED", "UPLOAD", "OSINT_SURFACE", "OSINT_DARK", "CHAIN", "TELEGRAM", "REPORT"
]
Origin = Literal["UPLOAD", "CAPTURE", "MONITOR", "DERIVATIVE", "REPORT"]
EvidenceStatus = Literal["PROCESSING", "READY", "PARTIAL", "QUARANTINED", "FAILED", "EXPIRED"]
EvidenceKind = Literal[
    "PDF",
    "HTML",
    "WARC",
    "IMAGE",
    "CSV",
    "JSON",
    "TEXT",
    "ZIP",
    "AUDIO",
    "VIDEO",
    "OFFICE",
    "UNKNOWN",
]
DerivativeKind = Literal["TEXT", "OCR", "TRANSCRIPT", "IMAGE_META", "ROWS", "MESSAGES", "HTML_SAFE"]
CustodyAction = Literal[
    "INGESTED", "VERIFIED", "DERIVED", "VIEWED_ORIGINAL", "EXPORTED", "QUARANTINED", "RELEASED"
]
ObservationType = Literal[
    "SUBSTANCE",
    "SLANG",
    "VENDOR_ALIAS",
    "MARKETPLACE",
    "LOCATION",
    "SHIPPING_TERM",
    "PACKAGING_TERM",
    "PRICE",
    "QUANTITY",
    "CURRENCY",
    "CONTACT_HANDLE",
    "EMAIL",
    "PHONE",
    "PGP_KEY",
    "PGP_FINGERPRINT",
    "BTC_ADDRESS",
    "ETH_ADDRESS",
    "XMR_ADDRESS",
    "TRON_ADDRESS",
    "URL",
    "ONION_LOCATOR",
    "IMAGE_REFERENCE",
    "SLANG_CANDIDATE",
]
RunStatus = Literal["QUEUED", "RUNNING", "DONE", "ERROR", "CANCELLED", "BUDGET"]
CandidateStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "DEFERRED"]
Band = Literal["WEAK", "POSSIBLE", "LEAD", "STRONG"]
EdgeType = Literal[
    "CO_OCCURS",
    "USES",
    "POSSIBLE_SAME_OPERATOR",
    "ANALYST_CONFIRMED_RELATED",
    "MENTIONS_LOCATION",
    "CONTAINS",
]
EdgeStatus = Literal["PENDING", "CONFIRMED", "REJECTED", "INFO"]
DecisionTarget = Literal["LINK", "ACTIVITY", "ALERT", "FINDING"]
DecisionValue = Literal["ACCEPT", "REJECT", "DEFER", "REQUEST_MORE_EVIDENCE"]
FindingKind = Literal["OBSERVED", "MODEL", "CANDIDATE", "CONFIRMED"]
FindingStatus = Literal["DRAFT", "PROMOTED", "SUPERSEDED"]
ThreadStatus = Literal["OPEN", "CLOSED"]
Harness = Literal["CLAUDE", "OFFLINE", "FAKE", "DETERMINISTIC"]
MessageRole = Literal["USER", "ASSISTANT", "SYSTEM", "TOOL"]
ItemType = Literal[
    "KEYWORD",
    "ALIAS",
    "WALLET",
    "PGP_FINGERPRINT",
    "ONION_DOMAIN",
    "TELEGRAM_CHANNEL",
    "IMAGE_HASH",
]
AlertKind = Literal[
    "NEW_HIT",
    "TREND",
    "WALLET_ACTIVITY",
    "KEY_CHANGE",
    "ONION_STATUS",
    "IMAGE_MATCH",
    "MONITOR_ERROR",
    "OVERFLOW",
]
AlertStatus = Literal["OPEN", "ACKNOWLEDGED", "DISMISSED", "ESCALATED"]
ActorKind = Literal["USER", "TOKEN", "SYSTEM", "MODEL"]
RequesterKind = Literal["USER", "THREAD", "WATCHLIST_ITEM", "SYSTEM"]


class Span(Schema):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    line: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class EvidenceRef(Schema):
    id: UUID
    code: str


T = TypeVar("T")


class Page[T](Schema):
    items: list[T]
    next_cursor: str | None = None
    total: int | None = None


class ActorRef(Schema):
    kind: ActorKind
    id: UUID | None = None
    display: str


class ErrorBody(Schema):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorEnvelope(Schema):
    error: ErrorBody


class Rationale(Schema):
    rationale: str = Field(min_length=1)


class Reason(Schema):
    reason: str = Field(min_length=1)


class JobRef(Schema):
    job_id: str


class FindingRef(Schema):
    id: UUID
    title: str
    kind: FindingKind


class ResourceRef(Schema):
    type: str
    id: UUID
