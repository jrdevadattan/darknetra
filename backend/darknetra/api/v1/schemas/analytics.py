from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .common import Band, CandidateStatus, EdgeStatus, EdgeType, EvidenceRef, Page, Schema
from .entities import Entity, Observation
from .evidence import Evidence
from .findings import Decision


class FeatureContribution(Schema):
    name: str = Field(min_length=1, max_length=200)
    family: str
    value: float
    weight: float
    contribution: float
    evidence: list[EvidenceRef]
    explanation: str


class LinkCandidate(Schema):
    id: UUID
    subject_a: Entity
    subject_b: Entity
    score: int
    band: Band
    families: list[str]
    features: list[FeatureContribution]
    contradictions: list[dict[str, Any]]
    status: CandidateStatus
    version: int
    supersedes_id: UUID | None = None
    decision: Decision | None = None
    run_id: UUID
    rescored: bool


class ActivityCandidate(Schema):
    id: UUID
    evidence: EvidenceRef
    score: float
    label: str
    features: list[FeatureContribution]
    status: CandidateStatus


class GraphNode(Schema):
    id: UUID
    type: str
    label: str
    status: str
    degree: int
    meta: dict[str, Any]


class GraphEdge(Schema):
    id: UUID
    source: UUID
    target: UUID
    type: EdgeType
    status: EdgeStatus
    score: float | None = None
    families: list[str]
    candidate_id: UUID | None = None
    decision_id: UUID | None = None
    first_seen_at: datetime
    last_seen_at: datetime


class GraphDTO(Schema):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    focus: UUID | None = None


class EdgeProvenance(Schema):
    edge: GraphEdge
    evidence: list[Evidence]
    candidate: LinkCandidate | None = None
    decision: Decision | None = None


class WalletAssessRequest(Schema):
    address: str = Field(min_length=1, max_length=256)
    chain: Literal["btc", "eth", "tron", "xmr"] | None = None
    live: bool = False


class GnnAssessment(Schema):
    prediction: str
    class_: int
    illicit_probability: float
    licit_probability: float
    threshold: float
    model_version: str
    n_nodes: int
    caveat: str


class SanctionsAssessment(Schema):
    sanctioned: bool
    source: str
    program: str | None = None
    entity: str | None = None
    list_version: str


class WalletAssessment(Schema):
    id: UUID
    address: str = Field(min_length=1, max_length=256)
    chain: str
    gnn: GnnAssessment | None = None
    gnn_unavailable_reason: str | None = None
    sanctions: SanctionsAssessment | None = None
    live_summary: dict[str, Any] | None = None
    live_summary_evidence: EvidenceRef | None = None
    tags: list[str]
    traceable: bool
    assessed_at: datetime
    version: int


class TrendPoint(Schema):
    day: date
    count: int
    unique_evidence_families: int
    unique_aliases: int
    unique_sources: int
    z: float | None = None


class TrendSeries(Schema):
    term: str
    type: str
    points: list[TrendPoint]
    candidate: bool
    reasons: list[str]


class NewTermCandidate(Schema):
    term: str
    frequency: int
    diversity: int
    score: float


class Trends(Schema):
    window_days: int
    series: list[TrendSeries]
    new_term_candidates: list[NewTermCandidate]


class CorrelateRequest(Schema):
    focus_entity_id: UUID | None = None


class CorrelateResult(Schema):
    run_id: UUID
    candidates_created: int
    candidates_rescored: int


class EntityDetail(Entity):
    observations: Page[Observation]
    edges: list[GraphEdge]
