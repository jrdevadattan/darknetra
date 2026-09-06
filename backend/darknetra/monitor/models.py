"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("case_id", "id"),)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    watchlist_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_norm: Mapped[str] = mapped_column(Text, nullable=False)
    variants: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "type", "value_norm"),
        ForeignKeyConstraint(
            ["case_id", "watchlist_id"],
            ["watchlists.case_id", "watchlists.id"],
            name="fk_monitor_watchlist_id_watchlists",
        ),
        CheckConstraint(
            "type IN ('KEYWORD', 'ALIAS', 'WALLET', 'PGP_FINGERPRINT', 'ONION_DOMAIN', 'TELEGRAM_CHANNEL', 'IMAGE_HASH')",
            name="type",
        ),
    )


class MonitorRun(Base):
    __tablename__ = "monitor_runs"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sources_run: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    new_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "item_id"],
            ["watchlist_items.case_id", "watchlist_items.id"],
            name="fk_monitor_item_id_watchlist_items",
        ),
    )


class MonitorHit(Base):
    __tablename__ = "monitor_hits"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    url_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    alertable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasons: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    alert_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("item_id", "content_hash"),
        ForeignKeyConstraint(
            ["case_id", "run_id"],
            ["monitor_runs.case_id", "monitor_runs.id"],
            name="fk_monitor_run_id_monitor_runs",
        ),
        ForeignKeyConstraint(
            ["case_id", "item_id"],
            ["watchlist_items.case_id", "watchlist_items.id"],
            name="fk_monitor_item_id_watchlist_items",
        ),
        ForeignKeyConstraint(
            ["case_id", "evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_monitor_evidence_id_evidence",
        ),
        ForeignKeyConstraint(
            ["case_id", "alert_id"],
            ["alerts.case_id", "alerts.id"],
            name="fk_monitor_alert_id_alerts",
        ),
    )


class MonitorSeenUrl(Base):
    __tablename__ = "monitor_seen_urls"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    url_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "item_id"],
            ["watchlist_items.case_id", "watchlist_items.id"],
            name="fk_monitor_item_id_watchlist_items",
        ),
    )


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    diversity: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    config_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="OPEN", server_default="OPEN")
    finding_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    assigned_to: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        CheckConstraint(
            "kind IN ('NEW_HIT', 'TREND', 'WALLET_ACTIVITY', 'KEY_CHANGE', 'ONION_STATUS', 'IMAGE_MATCH', 'MONITOR_ERROR', 'OVERFLOW')",
            name="kind",
        ),
        ForeignKeyConstraint(
            ["case_id", "item_id"],
            ["watchlist_items.case_id", "watchlist_items.id"],
            name="fk_monitor_item_id_watchlist_items",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'DISMISSED', 'ESCALATED')", name="status"
        ),
        ForeignKeyConstraint(
            ["case_id", "finding_id"],
            ["findings.case_id", "findings.id"],
            name="fk_monitor_finding_id_findings",
        ),
        ForeignKeyConstraint(
            ["case_id", "decision_id"],
            ["decisions.case_id", "decisions.id"],
            name="fk_monitor_decision_id_decisions",
        ),
    )
