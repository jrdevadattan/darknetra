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

from darknetra_api.db.base import Base
from darknetra_api.models.user import utc_now


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


class EvidenceSensitiveValueKind(StrEnum):
    SOURCE_LOCATOR = "SOURCE_LOCATOR"
    AUTHORITY_REFERENCE = "AUTHORITY_REFERENCE"
    PROTECTED_NOTE = "PROTECTED_NOTE"
    CUSTODY_NOTE = "CUSTODY_NOTE"
    CONTACT = "CONTACT"
    POLICY_RESTRICTED_WALLET = "POLICY_RESTRICTED_WALLET"


EVIDENCE_SOURCE_CLASS_ENUM = sa.Enum(EvidenceSourceClass, name="evidence_source_class")
EVIDENCE_STATE_ENUM = sa.Enum(EvidenceState, name="evidence_state")
EVIDENCE_SENSITIVE_VALUE_KIND_ENUM = sa.Enum(
    EvidenceSensitiveValueKind,
    name="evidence_sensitive_value_kind",
)


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        sa.UniqueConstraint("id", "case_id", name="uq_evidence_artifact_case"),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0", name="ck_evidence_size_nonnegative"
        ),
        sa.CheckConstraint(
            "sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_evidence_sha256_hex",
        ),
        sa.CheckConstraint(
            "sha512 IS NULL OR sha512 ~ '^[0-9a-f]{128}$'",
            name="ck_evidence_sha512_hex",
        ),
        sa.CheckConstraint(
            "state = 'STAGING' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL "
            "AND object_key IS NOT NULL AND btrim(object_key) <> '')",
            name="ck_evidence_manifest_complete_after_staging",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_class: Mapped[EvidenceSourceClass] = mapped_column(
        EVIDENCE_SOURCE_CLASS_ENUM,
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    acquisition_method: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    collector_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    captured_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    original_timezone: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    media_type: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)
    sha512: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    object_key: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
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
    policy_restricted: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    allow_original_download: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
        onupdate=utc_now,
    )


class EvidenceSensitiveValue(Base):
    __tablename__ = "evidence_sensitive_values"
    __table_args__ = (
        sa.UniqueConstraint(
            "id",
            "evidence_id",
            "case_id",
            "kind",
            name="uq_evidence_sensitive_value_identity_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            ondelete="CASCADE",
            name="fk_evidence_sensitive_value_artifact_case",
        ),
        sa.CheckConstraint(
            "blind_index IS NULL OR blind_index ~ '^[0-9a-f]{64}$'",
            name="ck_evidence_sensitive_blind_index_hex",
        ),
        sa.CheckConstraint(
            "key_version ~ '^v[1-9][0-9]{0,62}$'",
            name="ck_evidence_sensitive_key_version",
        ),
        sa.CheckConstraint(
            "nonce_b64 ~ '^[A-Za-z0-9+/]{16}$' "
            "AND octet_length(decode(nonce_b64, 'base64')) = 12 "
            "AND translate(encode(decode(nonce_b64, 'base64'), 'base64'), E'\\n\\r', '') "
            "= nonce_b64",
            name="ck_evidence_sensitive_nonce_b64",
        ),
        sa.CheckConstraint(
            "ciphertext_b64 ~ '^([A-Za-z0-9+/]{4})*"
            "([A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$' "
            "AND octet_length(decode(ciphertext_b64, 'base64')) >= 16 "
            "AND translate(encode(decode(ciphertext_b64, 'base64'), 'base64'), E'\\n\\r', '') "
            "= ciphertext_b64",
            name="ck_evidence_sensitive_ciphertext_b64",
        ),
        sa.CheckConstraint(
            "(kind = 'SOURCE_LOCATOR' AND blind_index IS NOT NULL) OR "
            "(kind <> 'SOURCE_LOCATOR' AND blind_index IS NULL)",
            name="ck_evidence_sensitive_blind_index_policy",
        ),
        sa.Index(
            "uq_evidence_source_locator_blind_index",
            "case_id",
            "blind_index",
            unique=True,
            postgresql_where=sa.text("kind = 'SOURCE_LOCATOR' AND blind_index IS NOT NULL"),
        ),
    )
    __repr__ = object.__repr__

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    kind: Mapped[EvidenceSensitiveValueKind] = mapped_column(
        EVIDENCE_SENSITIVE_VALUE_KIND_ENUM,
        nullable=False,
        index=True,
    )
    key_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    nonce_b64: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    ciphertext_b64: Mapped[str] = mapped_column(sa.Text, nullable=False)
    blind_index: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    contact_kind: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    wallet_network: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    wallet_asset: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    policy_sensitive: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
    )

    def envelope_mapping(self) -> dict[str, str]:
        return {
            "key_version": self.key_version,
            "nonce_b64": self.nonce_b64,
            "ciphertext_b64": self.ciphertext_b64,
        }


class EvidenceDerivation(Base):
    __tablename__ = "evidence_derivations"
    __table_args__ = (
        sa.CheckConstraint(
            "parent_evidence_id <> child_evidence_id",
            name="ck_evidence_derivation_not_self",
        ),
        sa.CheckConstraint(
            "parameters_digest = darknetra_derivation_parameters_digest(parameters_json)",
            name="ck_evidence_derivation_parameters_digest",
        ),
        sa.UniqueConstraint(
            "parent_evidence_id",
            "transformation",
            "transformer_version",
            "parameters_digest",
            name="uq_evidence_derivation_work_identity",
        ),
        sa.ForeignKeyConstraint(
            ["parent_evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            ondelete="CASCADE",
            name="fk_evidence_derivation_parent_case",
        ),
        sa.ForeignKeyConstraint(
            ["child_evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            ondelete="CASCADE",
            name="fk_evidence_derivation_child_case",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    child_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    transformation: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    transformer_version: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    parameters_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
    )


@event.listens_for(EvidenceArtifact, "before_update")
def _prevent_preserved_manifest_rewrite(
    mapper: Mapper[Any], connection: Any, target: EvidenceArtifact
) -> None:
    del mapper, connection
    inspection = sa.inspect(target)
    state_history = inspection.attrs.state.history
    old_state = state_history.deleted[0] if state_history.deleted else target.state
    if old_state != EvidenceState.STAGING and target.state == EvidenceState.STAGING:
        from darknetra_api.services.evidence import EvidenceDigestImmutableError

        raise EvidenceDigestImmutableError("preserved evidence cannot return to staging")
    if old_state == EvidenceState.STAGING:
        return
    for attribute_name in ("size_bytes", "sha256", "sha512", "object_key"):
        history = inspection.attrs[attribute_name].history
        if history.has_changes():
            from darknetra_api.services.evidence import EvidenceDigestImmutableError

            raise EvidenceDigestImmutableError("preserved evidence manifest cannot be rewritten")


@event.listens_for(EvidenceSensitiveValue, "before_insert")
@event.listens_for(EvidenceSensitiveValue, "before_update")
def _validate_sensitive_value_storage(
    mapper: Mapper[Any], connection: Any, target: EvidenceSensitiveValue
) -> None:
    del mapper, connection
    from darknetra_api.services.evidence import validate_sensitive_value_storage

    validate_sensitive_value_storage(target)


@event.listens_for(EvidenceSensitiveValue, "load")
def _validate_loaded_sensitive_value(target: EvidenceSensitiveValue, context: Any) -> None:
    del context
    from darknetra_api.services.evidence import validate_sensitive_value_storage

    validate_sensitive_value_storage(target)


@event.listens_for(EvidenceSensitiveValue, "refresh")
def _validate_refreshed_sensitive_value(
    target: EvidenceSensitiveValue, context: Any, attrs: Any
) -> None:
    del context, attrs
    from darknetra_api.services.evidence import validate_sensitive_value_storage

    validate_sensitive_value_storage(target)


@event.listens_for(EvidenceDerivation, "before_insert")
@event.listens_for(EvidenceDerivation, "before_update")
def _validate_derivation_parameters(
    mapper: Mapper[Any], connection: Any, target: EvidenceDerivation
) -> None:
    del mapper, connection
    from darknetra_api.services.provenance import derivation_parameters_digest

    expected = derivation_parameters_digest(target.parameters_json)
    if target.parameters_digest != expected:
        raise ValueError("derivation parameters digest does not match canonical parameters")


@event.listens_for(EvidenceDerivation, "load")
@event.listens_for(EvidenceDerivation, "refresh")
def _validate_loaded_derivation_parameters(
    target: EvidenceDerivation, context: Any, attrs: Any = None
) -> None:
    del context, attrs
    from darknetra_api.services.provenance import derivation_parameters_digest

    expected = derivation_parameters_digest(target.parameters_json)
    if target.parameters_digest != expected:
        raise ValueError("derivation parameters digest does not match canonical parameters")
