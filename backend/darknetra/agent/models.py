"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class Thread(Base):
    __tablename__ = "threads"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="OPEN", server_default="OPEN")
    harness: Mapped[str] = mapped_column(
        Text, nullable=False, default="DETERMINISTIC", server_default="DETERMINISTIC"
    )
    harness_session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_finding_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    budget_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=2)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    assignee_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="status"),
        CheckConstraint(
            "harness IN ('CLAUDE', 'NIM', 'OFFLINE', 'FAKE', 'DETERMINISTIC')", name="harness"
        ),
    )


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="QUEUED", server_default="QUEUED"
    )
    harness: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    replayed_from_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "thread_id"],
            ["threads.case_id", "threads.id"],
            name="fk_agent_thread_id_threads",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'DONE', 'ERROR', 'CANCELLED', 'BUDGET')", name="status"
        ),
        CheckConstraint(
            "harness IN ('CLAUDE', 'NIM', 'OFFLINE', 'FAKE', 'DETERMINISTIC')", name="harness"
        ),
        ForeignKeyConstraint(
            ["case_id", "replayed_from_run_id"],
            ["runs.case_id", "runs.id"],
            name="fk_agent_replayed_from_run_id_runs",
        ),
        Index(
            "uq_runs_active_thread",
            "thread_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    blocks: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    verification: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    harness: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "thread_id"],
            ["threads.case_id", "threads.id"],
            name="fk_agent_thread_id_threads",
        ),
        ForeignKeyConstraint(
            ["case_id", "run_id"], ["runs.case_id", "runs.id"], name="fk_agent_run_id_runs"
        ),
        CheckConstraint("role IN ('USER', 'ASSISTANT', 'SYSTEM', 'TOOL')", name="role"),
        CheckConstraint(
            "harness IN ('CLAUDE', 'NIM', 'OFFLINE', 'FAKE', 'DETERMINISTIC')", name="harness"
        ),
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    args_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy_decision: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_evidence_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    error: Mapped[Any | None] = mapped_column(JSONB, nullable=True, default=dict)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requester_kind: Mapped[str] = mapped_column(Text, nullable=False)
    requester_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "run_id"], ["runs.case_id", "runs.id"], name="fk_agent_run_id_runs"
        ),
        ForeignKeyConstraint(
            ["case_id", "thread_id"],
            ["threads.case_id", "threads.id"],
            name="fk_agent_thread_id_threads",
        ),
        CheckConstraint(
            "requester_kind IN ('USER', 'THREAD', 'WATCHLIST_ITEM', 'SYSTEM')",
            name="requester_kind",
        ),
    )


class RunEvent(Base):
    __tablename__ = "run_events"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "run_id"], ["runs.case_id", "runs.id"], name="fk_agent_run_id_runs"
        ),
    )


class ReplayEntry(Base):
    __tablename__ = "replay_entries"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    question_norm: Mapped[str] = mapped_column(Text, nullable=False)
    harness: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_log: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "question_norm", "harness"),
        CheckConstraint(
            "harness IN ('CLAUDE', 'NIM', 'OFFLINE', 'FAKE', 'DETERMINISTIC')", name="harness"
        ),
        ForeignKeyConstraint(
            ["case_id", "run_id"], ["runs.case_id", "runs.id"], name="fk_agent_run_id_runs"
        ),
    )


class RateCounter(Base):
    __tablename__ = "rate_counters"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True, index=True
    )
    rate_key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
