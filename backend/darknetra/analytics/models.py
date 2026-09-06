"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class AnalyticRun(Base):
    __tablename__ = "analytic_runs"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    config_digest: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    stats: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("case_id", "id"),)


class LinkCandidate(Base):
    __tablename__ = "link_candidates"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    subject_a_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    subject_b_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(Text, nullable=False)
    features: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    evidence_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    contradictions: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    families: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="PENDING", server_default="PENDING"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    feature_digest: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "subject_a_id", "subject_b_id", "version"),
        ForeignKeyConstraint(
            ["case_id", "run_id"],
            ["analytic_runs.case_id", "analytic_runs.id"],
            name="fk_analytics_run_id_analytic_runs",
        ),
        ForeignKeyConstraint(
            ["case_id", "subject_a_id"],
            ["canonical_entities.case_id", "canonical_entities.id"],
            name="fk_analytics_subject_a_id_canonical_entities",
        ),
        ForeignKeyConstraint(
            ["case_id", "subject_b_id"],
            ["canonical_entities.case_id", "canonical_entities.id"],
            name="fk_analytics_subject_b_id_canonical_entities",
        ),
        CheckConstraint("band IN ('WEAK', 'POSSIBLE', 'LEAD', 'STRONG')", name="band"),
        CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'DEFERRED')", name="status"),
        ForeignKeyConstraint(
            ["case_id", "supersedes_id"],
            ["link_candidates.case_id", "link_candidates.id"],
            name="fk_analytics_supersedes_id_link_candidates",
        ),
        CheckConstraint("subject_a_id < subject_b_id", name="ordered_subjects"),
    )


class ActivityCandidate(Base):
    __tablename__ = "activity_candidates"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    features: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="PENDING", server_default="PENDING"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "evidence_id", "version"),
        ForeignKeyConstraint(
            ["case_id", "run_id"],
            ["analytic_runs.case_id", "analytic_runs.id"],
            name="fk_analytics_run_id_analytic_runs",
        ),
        ForeignKeyConstraint(
            ["case_id", "evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_analytics_evidence_id_evidence",
        ),
        CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'DEFERRED')", name="status"),
    )


class WalletAssessment(Base):
    __tablename__ = "wallet_assessments"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    address: Mapped[str] = mapped_column(Text, nullable=False)
    chain: Mapped[str] = mapped_column(Text, nullable=False)
    gnn: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    gnn_unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanctions: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    live_summary: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    live_summary_evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    traceable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    requested_by_kind: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "live_summary_evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_analytics_live_summary_evidence_id_evidence",
        ),
        CheckConstraint(
            "requested_by_kind IN ('USER', 'THREAD', 'WATCHLIST_ITEM', 'SYSTEM')",
            name="requested_by_kind",
        ),
    )


class TrendBucket(Base):
    __tablename__ = "trend_buckets"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True, index=True
    )
    subject_type: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_evidence_families: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_aliases: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_sources: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    src_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    dst_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    families: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    candidate_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    provenance: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "src_entity_id", "dst_entity_id", "type"),
        ForeignKeyConstraint(
            ["case_id", "src_entity_id"],
            ["canonical_entities.case_id", "canonical_entities.id"],
            name="fk_analytics_src_entity_id_canonical_entities",
        ),
        ForeignKeyConstraint(
            ["case_id", "dst_entity_id"],
            ["canonical_entities.case_id", "canonical_entities.id"],
            name="fk_analytics_dst_entity_id_canonical_entities",
        ),
        CheckConstraint(
            "type IN ('CO_OCCURS', 'USES', 'POSSIBLE_SAME_OPERATOR', 'ANALYST_CONFIRMED_RELATED', 'MENTIONS_LOCATION', 'CONTAINS')",
            name="type",
        ),
        CheckConstraint("status IN ('PENDING', 'CONFIRMED', 'REJECTED', 'INFO')", name="status"),
        ForeignKeyConstraint(
            ["case_id", "candidate_id"],
            ["link_candidates.case_id", "link_candidates.id"],
            name="fk_analytics_candidate_id_link_candidates",
        ),
        ForeignKeyConstraint(
            ["case_id", "decision_id"],
            ["decisions.case_id", "decisions.id"],
            name="fk_analytics_decision_id_decisions",
        ),
    )


class LedgerNode(Base):
    __tablename__ = "ledger_nodes"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True, index=True
    )
    node_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    txid: Mapped[str] = mapped_column(Text, nullable=False)
    timestep: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False, default=list)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (CheckConstraint("cardinality(features) = 102", name="feature_count"),)


class LedgerEdge(Base):
    __tablename__ = "ledger_edges"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True, index=True
    )
    src: Mapped[int] = mapped_column(Integer, primary_key=True)
    dst: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "src"],
            ["ledger_nodes.case_id", "ledger_nodes.node_index"],
            name="fk_analytics_src_ledger_nodes",
        ),
        ForeignKeyConstraint(
            ["case_id", "dst"],
            ["ledger_nodes.case_id", "ledger_nodes.node_index"],
            name="fk_analytics_dst_ledger_nodes",
        ),
    )


class LedgerAddress(Base):
    __tablename__ = "ledger_addresses"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True, index=True
    )
    address: Mapped[str] = mapped_column(Text, primary_key=True)
    chain: Mapped[str] = mapped_column(Text, nullable=False)
    node_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "node_index"],
            ["ledger_nodes.case_id", "ledger_nodes.node_index"],
            name="fk_analytics_node_index_ledger_nodes",
        ),
    )
