"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    supersedes_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        Index(
            "uq_decisions_initial_target",
            "case_id",
            "target_type",
            "target_id",
            "target_version",
            unique=True,
            postgresql_where=text("supersedes_id IS NULL"),
        ),
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "target_type", "target_id", "target_version", "id"),
        CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id", name="no_self_supersession"
        ),
        CheckConstraint(
            "target_type IN ('LINK', 'ACTIVITY', 'ALERT', 'FINDING')", name="target_type"
        ),
        CheckConstraint(
            "decision IN ('ACCEPT', 'REJECT', 'DEFER', 'REQUEST_MORE_EVIDENCE')", name="decision"
        ),
        ForeignKeyConstraint(
            ["case_id", "target_type", "target_id", "target_version", "supersedes_id"],
            [
                "decisions.case_id",
                "decisions.target_type",
                "decisions.target_id",
                "decisions.target_version",
                "decisions.id",
            ],
            name="fk_decisions_supersedes_id_decisions",
        ),
        Index(
            "uq_decisions_supersedes",
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
        ),
    )


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    thread_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    method: Mapped[str] = mapped_column(Text, nullable=False)
    method_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="DRAFT", server_default="DRAFT"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    claim_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
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
            name="fk_decisions_thread_id_threads",
        ),
        CheckConstraint("kind IN ('OBSERVED', 'MODEL', 'CANDIDATE', 'CONFIRMED')", name="kind"),
        CheckConstraint("status IN ('DRAFT', 'PROMOTED', 'SUPERSEDED')", name="status"),
        ForeignKeyConstraint(
            ["case_id", "supersedes_id"],
            ["findings.case_id", "findings.id"],
            name="fk_decisions_supersedes_id_findings",
        ),
        ForeignKeyConstraint(
            ["case_id", "source_message_id"],
            ["messages.case_id", "messages.id"],
            name="fk_decisions_source_message_id_messages",
        ),
        ForeignKeyConstraint(
            ["case_id", "decision_id"],
            ["decisions.case_id", "decisions.id"],
            name="fk_decisions_decision_id_decisions",
        ),
    )
