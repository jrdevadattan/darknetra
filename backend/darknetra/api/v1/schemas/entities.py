from datetime import datetime
from typing import Any
from uuid import UUID

from .common import EvidenceRef, ObservationType, Schema, Span
from .evidence import Context


class Observation(Schema):
    id: UUID
    type: ObservationType
    raw: str
    normalized: Any
    evidence: EvidenceRef
    span: Span
    validator: str
    valid: bool
    confidence: float
    canonical_entity_id: UUID | None = None
    run_id: UUID
    meta: dict[str, Any]


class SampleSpan(Schema):
    evidence: EvidenceRef
    span: Span
    snippet: str


class Entity(Schema):
    id: UUID
    type: ObservationType
    value: str
    display: str
    first_seen_at: datetime
    last_seen_at: datetime
    observation_count: int
    sample_spans: list[SampleSpan]


class ExtractionRun(Schema):
    id: UUID
    evidence_id: UUID | None = None
    bundle_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict[str, Any]


class ExtractionRequest(Schema):
    evidence_id: UUID | None = None


class TaxonomyVariant(Schema):
    term: str
    language: str
    script: str
    note: str | None = None


class TaxonomyTermCreate(Schema):
    canonical: str
    type: ObservationType
    variants: list[TaxonomyVariant]
    active: bool = True


class TaxonomyTerm(TaxonomyTermCreate):
    id: UUID


class TaxonomyTermPatch(Schema):
    canonical: str | None = None
    type: ObservationType | None = None
    variants: list[TaxonomyVariant] | None = None
    active: bool | None = None


class ObservationDetail(Observation):
    context: Context
