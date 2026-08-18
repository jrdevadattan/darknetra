from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, Mapper, mapped_column
from sqlalchemy.types import TypeDecorator

from darknetra_api.db.base import Base
from darknetra_api.models.user import utc_now
from darknetra_api.security.encryption import EncryptedValue


class EvidenceSourceClass(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    RESEARCH_ARCHIVE = "RESEARCH_ARCHIVE"
    AUTHORIZED_IMPORT = "AUTHORIZED_IMPORT"
    PUBLIC_OBSERVATION = "PUBLIC_OBSERVATION"


class EvidenceState(StrEnum):
    STAGING = "STAGING"
    PRESERVED = "PRESERVED"
    QUARANTINED = "QUARANTINED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"


EVIDENCE_SOURCE_CLASS_ENUM = sa.Enum(EvidenceSourceClass, name="evidence_source_class")
EVIDENCE_STATE_ENUM = sa.Enum(EvidenceState, name="evidence_state")


class EncryptedValueType(TypeDecorator[EncryptedValue]):
    """Persist an authenticated encrypted envelope as JSONB without plaintext."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(
        self, value: EncryptedValue | None, dialect: sa.engine.Dialect
    ) -> dict[str, str] | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, EncryptedValue):
            raise TypeError("encrypted metadata must be an EncryptedValue")
        return {
            "key_version": value.key_version,
            "nonce_b64": value.nonce_b64,
            "ciphertext_b64": value.ciphertext_b64,
        }

    def process_result_value(
        self, value: dict[str, str] | None, dialect: sa.engine.Dialect
    ) -> EncryptedValue | None:
        del dialect
        if value is None:
            return None
        return EncryptedValue(
            key_version=value["key_version"],
            nonce_b64=value["nonce_b64"],
            ciphertext_b64=value["ciphertext_b64"],
        )


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_evidence_size_nonnegative"),
        sa.CheckConstraint(
            "sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_evidence_sha256_hex",
        ),
        sa.CheckConstraint(
            "sha512 IS NULL OR sha512 ~ '^[0-9a-f]{128}$'",
            name="ck_evidence_sha512_hex",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_class: Mapped[EvidenceSourceClass] = mapped_column(
        EVIDENCE_SOURCE_CLASS_ENUM, nullable=False
    )
    source_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    source_locator_ciphertext: Mapped[EncryptedValue | None] = mapped_column(
        EncryptedValueType(), nullable=True
    )
    source_locator_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)
    authority_reference_ciphertext: Mapped[EncryptedValue | None] = mapped_column(
        EncryptedValueType(), nullable=True
    )
    acquisition_method: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    collector_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    original_timezone: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    media_type: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)
    sha512: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    object_key: Mapped[str | None] = mapped_column(sa.String(180), nullable=True)
    state: Mapped[EvidenceState] = mapped_column(
        EVIDENCE_STATE_ENUM,
        nullable=False,
        default=EvidenceState.STAGING,
        server_default=EvidenceState.STAGING.value,
        index=True,
    )
    quarantine_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    tool_version: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    notes_ciphertext: Mapped[EncryptedValue | None] = mapped_column(
        EncryptedValueType(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
        onupdate=utc_now,
    )


class EvidenceDerivation(Base):
    __tablename__ = "evidence_derivations"
    __table_args__ = (
        sa.CheckConstraint(
            "parent_evidence_id <> child_evidence_id",
            name="ck_evidence_derivation_not_self",
        ),
        sa.UniqueConstraint(
            "parent_evidence_id",
            "child_evidence_id",
            "transformation",
            "transformer_version",
            name="uq_evidence_derivation_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    parent_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("evidence_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("evidence_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transformation: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    transformer_version: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now()
    )


@event.listens_for(EvidenceArtifact, "before_update")
def _prevent_preserved_digest_rewrite(
    mapper: Mapper[Any], connection: Any, target: EvidenceArtifact
) -> None:
    del mapper, connection
    inspection = sa.inspect(target)
    for attribute_name in ("sha256", "sha512"):
        history = inspection.attrs[attribute_name].history
        prior_values = [value for value in history.deleted if value is not None]
        if history.has_changes() and prior_values:
            from darknetra_api.services.evidence import EvidenceDigestImmutableError

            raise EvidenceDigestImmutableError(
                f"preserved evidence {attribute_name} cannot be rewritten"
            )
