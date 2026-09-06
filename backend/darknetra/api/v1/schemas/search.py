from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .common import EvidenceRef, Schema, SourceClass, Span


class SearchFilters(Schema):
    source_class: list[SourceClass] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    lang: list[str] = Field(default_factory=list)
    from_: datetime | None = Field(None, alias="from")
    to: datetime | None = None
    include_quarantined: bool = False


class SearchQuery(Schema):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal["hybrid", "lexical", "semantic"] = "hybrid"
    k: int = Field(8, ge=1, le=200)
    filters: SearchFilters = SearchFilters()


class SearchHit(Schema):
    evidence: EvidenceRef
    chunk_id: UUID
    span: Span
    snippet: str
    score: float
    source_class: SourceClass
    lang: str
    kind: str
    matched_terms: list[str]


class SearchResult(Schema):
    hits: list[SearchHit]
    mode_used: str
    dense_available: bool
    expansions: list[str]
