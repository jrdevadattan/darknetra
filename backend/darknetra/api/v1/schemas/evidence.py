from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from .common import (
    ActorRef,
    CustodyAction,
    DerivativeKind,
    ErrorBody,
    EvidenceKind,
    EvidenceRef,
    EvidenceStatus,
    Origin,
    RequesterKind,
    Schema,
    SourceClass,
    Span,
)


class RequesterRef(Schema):
    kind: RequesterKind
    id: UUID | None = None


class DerivativeSummary(Schema):
    id: UUID
    kind: DerivativeKind
    status: str
    extractor: str
    version: int
    lang_tags: list[str]
    script_tags: list[str]
    text_len: int | None = None


class CustodyEvent(Schema):
    action: CustodyAction
    actor: ActorRef
    at: datetime
    hash_verified: bool | None = None
    note: str | None = None


class Evidence(Schema):
    id: UUID
    code: str
    case_id: UUID
    sha256: str
    size_bytes: int
    mime: str
    kind: EvidenceKind
    original_filename: str
    source_class: SourceClass
    origin: Origin
    status: EvidenceStatus
    locator_display: str | None = None
    captured_at: datetime
    requested_by: RequesterRef | None = None
    parent: EvidenceRef | None = None
    warnings: list[str] = Field(default_factory=list)
    derivatives: list[DerivativeSummary] = Field(default_factory=list)
    custody: list[CustodyEvent] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class EvidenceIngestResult(Schema):
    evidence: Evidence
    duplicate: bool
    warnings: list[str] = Field(default_factory=list)


class UploadItemError(Schema):
    filename: str
    error: ErrorBody


class UploadResponse(Schema):
    results: list[EvidenceIngestResult]
    errors: list[UploadItemError]


class TextDerivative(Schema):
    text: str
    line_offsets: list[int]
    page_map: list[tuple[int, int]] | None = None
    contexts: list[dict[str, Any]] = Field(default_factory=list)


class HtmlSafeDerivative(Schema):
    html: str


class ParsedMessage(Schema):
    id: str | None = None
    sender: str | None = None
    text: str
    at: datetime | None = None
    reply_to: str | None = None
    edited_at: datetime | None = None
    media: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class MessagesDerivative(Schema):
    platform: str
    messages: list[ParsedMessage]


class RowsDerivative(Schema):
    header: list[str]
    rows: list[list[str]]
    truncated: bool


class ImageMetaDerivative(Schema):
    width: int
    height: int
    format: str
    exif_present: bool
    phash: str
    dhash: str


class Context(Schema):
    evidence: EvidenceRef
    span: Span
    text: str
    before: str
    after: str
    line_no: int | None = None


class VerifyResult(Schema):
    hash_verified: bool
