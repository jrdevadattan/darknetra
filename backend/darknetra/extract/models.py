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
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class TaxonomyTerm(Base):
    __tablename__ = "taxonomy_terms"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    canonical: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    script: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("canonical", "term", "language", "script"),
        CheckConstraint(
            "type IN ('SUBSTANCE', 'SLANG', 'VENDOR_ALIAS', 'MARKETPLACE', 'LOCATION', 'SHIPPING_TERM', 'PACKAGING_TERM', 'PRICE', 'QUANTITY', 'CURRENCY', 'CONTACT_HANDLE', 'EMAIL', 'PHONE', 'PGP_KEY', 'PGP_FINGERPRINT', 'BTC_ADDRESS', 'ETH_ADDRESS', 'XMR_ADDRESS', 'TRON_ADDRESS', 'URL', 'ONION_LOCATOR', 'IMAGE_REFERENCE', 'SLANG_CANDIDATE')",
            name="type",
        ),
    )


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    evidence_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    bundle_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    stats: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_extract_evidence_id_evidence",
        ),
        Index(
            "uq_extraction_bundle",
            "evidence_id",
            "bundle_version",
            unique=True,
            postgresql_where=text("evidence_id IS NOT NULL"),
        ),
    )


class CanonicalEntity(Base):
    __tablename__ = "canonical_entities"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    display: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attrs: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        UniqueConstraint("case_id", "type", "value"),
        CheckConstraint(
            "type IN ('SUBSTANCE', 'SLANG', 'VENDOR_ALIAS', 'MARKETPLACE', 'LOCATION', 'SHIPPING_TERM', 'PACKAGING_TERM', 'PRICE', 'QUANTITY', 'CURRENCY', 'CONTACT_HANDLE', 'EMAIL', 'PHONE', 'PGP_KEY', 'PGP_FINGERPRINT', 'BTC_ADDRESS', 'ETH_ADDRESS', 'XMR_ADDRESS', 'TRON_ADDRESS', 'URL', 'ONION_LOCATOR', 'IMAGE_REFERENCE', 'SLANG_CANDIDATE')",
            name="type",
        ),
    )


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    derivative_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    raw: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    canonical_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validator: Mapped[str] = mapped_column(Text, nullable=False)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    meta: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        ForeignKeyConstraint(
            ["case_id", "evidence_id"],
            ["evidence.case_id", "evidence.id"],
            name="fk_extract_evidence_id_evidence",
        ),
        ForeignKeyConstraint(
            ["case_id", "derivative_id"],
            ["derivatives.case_id", "derivatives.id"],
            name="fk_extract_derivative_id_derivatives",
        ),
        ForeignKeyConstraint(
            ["case_id", "run_id"],
            ["extraction_runs.case_id", "extraction_runs.id"],
            name="fk_extract_run_id_extraction_runs",
        ),
        CheckConstraint(
            "type IN ('SUBSTANCE', 'SLANG', 'VENDOR_ALIAS', 'MARKETPLACE', 'LOCATION', 'SHIPPING_TERM', 'PACKAGING_TERM', 'PRICE', 'QUANTITY', 'CURRENCY', 'CONTACT_HANDLE', 'EMAIL', 'PHONE', 'PGP_KEY', 'PGP_FINGERPRINT', 'BTC_ADDRESS', 'ETH_ADDRESS', 'XMR_ADDRESS', 'TRON_ADDRESS', 'URL', 'ONION_LOCATOR', 'IMAGE_REFERENCE', 'SLANG_CANDIDATE')",
            name="type",
        ),
        ForeignKeyConstraint(
            ["case_id", "canonical_entity_id"],
            ["canonical_entities.case_id", "canonical_entities.id"],
            name="fk_extract_canonical_entity_id_canonical_entities",
        ),
        CheckConstraint("span_end > span_start AND span_start >= 0", name="span"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
