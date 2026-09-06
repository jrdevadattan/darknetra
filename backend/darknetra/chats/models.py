from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base, Timestamps, UUIDPk


class PrivateThread(UUIDPk, Timestamps, Base):
    __tablename__ = "private_threads"
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="OPEN")
    provider: Mapped[str] = mapped_column(Text, default="AUTO")
    budget_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=2)
    spent_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_user_id", "id"),
        CheckConstraint("status IN ('OPEN','CLOSED')", name="status"),
        CheckConstraint("budget_usd >= 0 AND spent_usd >= 0", name="budget"),
    )


class PrivateRun(UUIDPk, Base):
    __tablename__ = "private_runs"
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(Text, default="QUEUED")
    provider: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Any | None] = mapped_column(JSONB)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("owner_user_id", "id"),
        UniqueConstraint("owner_user_id", "thread_id", "id"),
        ForeignKeyConstraint(
            ["owner_user_id", "thread_id"], ["private_threads.owner_user_id", "private_threads.id"]
        ),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','DONE','ERROR','CANCELLED','BUDGET')", name="status"
        ),
        Index(
            "uq_private_runs_active_thread",
            "thread_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
        ),
    )


class PrivateMessage(UUIDPk, Base):
    __tablename__ = "private_messages"
    owner_user_id: Mapped[UUID] = mapped_column(index=True)
    thread_id: Mapped[UUID]
    run_id: Mapped[UUID | None]
    role: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    blocks: Mapped[Any] = mapped_column(JSONB, default=list)
    provider: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "thread_id"], ["private_threads.owner_user_id", "private_threads.id"]
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "thread_id", "run_id"],
            ["private_runs.owner_user_id", "private_runs.thread_id", "private_runs.id"],
        ),
        CheckConstraint("role IN ('USER','ASSISTANT','SYSTEM')", name="role"),
    )


class PrivateRunEvent(Base):
    __tablename__ = "private_run_events"
    owner_user_id: Mapped[UUID] = mapped_column(index=True)
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    data: Mapped[Any] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "run_id"], ["private_runs.owner_user_id", "private_runs.id"]
        ),
    )
