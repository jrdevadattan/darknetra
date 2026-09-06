"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_class: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="PROCESSING", server_default="PROCESSING"
    )
    locator_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    locator_bidx: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    requested_by_kind: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    parent_evidence_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    transformation: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    meta: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "code"),
        UniqueConstraint("case_id", "sha256"),
        CheckConstraint(
            "kind IN ('PDF', 'HTML', 'WARC', 'IMAGE', 'CSV', 'JSON', 'TEXT', 'ZIP', 'AUDIO', 'VIDEO', 'OFFICE', 'UNKNOWN')",
            name="kind",
        ),
        CheckConstraint(
            "source_class IN ('SYNTHETIC', 'SEIZED', 'UPLOAD', 'OSINT_SURFACE', 'OSINT_DARK', 'CHAIN', 'TELEGRAM', 'REPORT')",
            name="source_class",
        ),
        CheckConstraint(
            "origin IN ('UPLOAD', 'CAPTURE', 'MONITOR', 'DERIVATIVE', 'REPORT')", name="origin"
        ),
        CheckConstraint(
            "status IN ('PROCESSING', 'READY', 'PARTIAL', 'QUARANTINED', 'FAILED', 'EXPIRED')",
            name="status",
        ),
        CheckConstraint(
            "requested_by_kind IN ('USER', 'THREAD', 'WATCHLIST_ITEM', 'SYSTEM')",
            name="requested_by_kind",
        ),
        ForeignKeyConstraint(
            ["case_id", "parent_evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_evidence_parent_evidence_id_evidence",
        ),
        CheckConstraint(
            "created_by_kind IN ('USER', 'TOKEN', 'SYSTEM', 'MODEL')", name="created_by_kind"
        ),
    )


class CustodyEvent(Base):
    __tablename__ = "custody_events"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    hash_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_evidence_evidence_id_evidence",
        ),
        CheckConstraint(
            "action IN ('INGESTED', 'VERIFIED', 'DERIVED', 'VIEWED_ORIGINAL', 'EXPORTED', 'QUARANTINED', 'RELEASED')",
            name="action",
        ),
        CheckConstraint("actor_kind IN ('USER', 'TOKEN', 'SYSTEM', 'MODEL')", name="actor_kind"),
    )


class Derivative(Base):
    __tablename__ = "derivatives"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    extractor: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    lang_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    script_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    text_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("evidence_id", "kind", "version"),
        ForeignKeyConstraint(
            ["case_id", "evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_evidence_evidence_id_evidence",
        ),
        CheckConstraint(
            "kind IN ('TEXT', 'OCR', 'TRANSCRIPT', 'IMAGE_META', 'ROWS', 'MESSAGES', 'HTML_SAFE')",
            name="kind",
        ),
    )


class EvidenceCodeCounter(Base):
    __tablename__ = "evidence_code_counters"
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True, index=True
    )
    next: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
