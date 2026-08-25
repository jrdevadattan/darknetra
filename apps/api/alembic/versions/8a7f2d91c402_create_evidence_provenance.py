"""create evidence provenance

Revision ID: 8a7f2d91c402
Revises: 3f21c6d4a901
Create Date: 2026-08-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8a7f2d91c402"
down_revision: str | Sequence[str] | None = "3f21c6d4a901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    source_class = sa.Enum(
        "SYNTHETIC",
        "RESEARCH_ARCHIVE",
        "AUTHORIZED_IMPORT",
        "PUBLIC_OBSERVATION",
        name="evidence_source_class",
    )
    state = sa.Enum(
        "STAGING",
        "PRESERVED",
        "QUARANTINED",
        "PROCESSING",
        "READY",
        "PARTIAL",
        "FAILED",
        "INTEGRITY_MISMATCH",
        name="evidence_state",
    )
    sensitive_kind = sa.Enum(
        "SOURCE_LOCATOR",
        "AUTHORITY_REFERENCE",
        "PROTECTED_NOTE",
        "CUSTODY_NOTE",
        "CONTACT",
        "POLICY_RESTRICTED_WALLET",
        name="evidence_sensitive_value_kind",
    )
    op.create_table(
        "evidence_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("source_class", source_class, nullable=False),
        sa.Column("source_type", sa.String(length=120), nullable=False),
        sa.Column("acquisition_method", sa.String(length=160), nullable=False),
        sa.Column("collector_user_id", sa.UUID(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_timezone", sa.String(length=80), nullable=True),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("sha512", sa.String(length=128), nullable=True),
        sa.Column("object_key", sa.String(length=255), nullable=True),
        sa.Column("state", state, server_default="STAGING", nullable=False),
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("tool_version", sa.String(length=80), nullable=True),
        sa.Column("policy_restricted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "allow_original_download",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["collector_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "case_id", name="uq_evidence_artifact_case"),
    )
    op.create_index(op.f("ix_evidence_artifacts_case_id"), "evidence_artifacts", ["case_id"])
    op.create_index(
        op.f("ix_evidence_artifacts_collector_user_id"),
        "evidence_artifacts",
        ["collector_user_id"],
    )
    op.create_index(op.f("ix_evidence_artifacts_sha256"), "evidence_artifacts", ["sha256"])
    op.create_index(op.f("ix_evidence_artifacts_state"), "evidence_artifacts", ["state"])

    op.create_table(
        "evidence_sensitive_values",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.Column("kind", sensitive_kind, nullable=False),
        sa.Column("key_version", sa.String(length=64), nullable=False),
        sa.Column("nonce_b64", sa.String(length=32), nullable=False),
        sa.Column("ciphertext_b64", sa.Text(), nullable=False),
        sa.Column("blind_index", sa.String(length=64), nullable=True),
        sa.Column("contact_kind", sa.String(length=40), nullable=True),
        sa.Column("wallet_network", sa.String(length=40), nullable=True),
        sa.Column("wallet_asset", sa.String(length=40), nullable=True),
        sa.Column("policy_sensitive", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "blind_index IS NULL OR blind_index ~ '^[0-9a-f]{64}$'",
            name="ck_evidence_sensitive_blind_index_hex",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            name="fk_evidence_sensitive_value_artifact_case",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "evidence_id",
            "case_id",
            name="uq_evidence_sensitive_value_artifact_case",
        ),
        sa.UniqueConstraint(
            "evidence_id",
            "kind",
            name="uq_evidence_sensitive_value_artifact_kind",
        ),
    )
    op.create_index(
        op.f("ix_evidence_sensitive_values_case_id"),
        "evidence_sensitive_values",
        ["case_id"],
    )
    op.create_index(
        op.f("ix_evidence_sensitive_values_evidence_id"),
        "evidence_sensitive_values",
        ["evidence_id"],
    )
    op.create_index(
        op.f("ix_evidence_sensitive_values_kind"),
        "evidence_sensitive_values",
        ["kind"],
    )
    op.create_index(
        "uq_evidence_source_locator_blind_index",
        "evidence_sensitive_values",
        ["case_id", "blind_index"],
        unique=True,
        postgresql_where=sa.text("kind = 'SOURCE_LOCATOR' AND blind_index IS NOT NULL"),
    )

    op.create_table(
        "evidence_derivations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("parent_evidence_id", sa.UUID(), nullable=False),
        sa.Column("child_evidence_id", sa.UUID(), nullable=False),
        sa.Column("transformation", sa.String(length=120), nullable=False),
        sa.Column("transformer_version", sa.String(length=80), nullable=False),
        sa.Column(
            "parameters_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "parent_evidence_id <> child_evidence_id",
            name="ck_evidence_derivation_not_self",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            name="fk_evidence_derivation_parent_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            name="fk_evidence_derivation_child_case",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_evidence_id",
            "child_evidence_id",
            "transformation",
            "transformer_version",
            name="uq_evidence_derivation_identity",
        ),
    )
    op.create_index(op.f("ix_evidence_derivations_case_id"), "evidence_derivations", ["case_id"])
    op.create_index(
        op.f("ix_evidence_derivations_child_evidence_id"),
        "evidence_derivations",
        ["child_evidence_id"],
    )
    op.create_index(
        op.f("ix_evidence_derivations_parent_evidence_id"),
        "evidence_derivations",
        ["parent_evidence_id"],
    )

    op.create_table(
        "custody_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("integrity_sha256", sa.String(length=64), nullable=True),
        sa.Column("sensitive_note_id", sa.UUID(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "integrity_sha256 IS NULL OR integrity_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_custody_integrity_sha256_hex",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            name="fk_custody_event_artifact_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sensitive_note_id", "evidence_id", "case_id"],
            [
                "evidence_sensitive_values.id",
                "evidence_sensitive_values.evidence_id",
                "evidence_sensitive_values.case_id",
            ],
            name="fk_custody_event_sensitive_note_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_custody_events_action"), "custody_events", ["action"])
    op.create_index(op.f("ix_custody_events_actor_user_id"), "custody_events", ["actor_user_id"])
    op.create_index(op.f("ix_custody_events_case_id"), "custody_events", ["case_id"])
    op.create_index(op.f("ix_custody_events_created_at"), "custody_events", ["created_at"])
    op.create_index(op.f("ix_custody_events_evidence_id"), "custody_events", ["evidence_id"])
    op.create_index(op.f("ix_custody_events_request_id"), "custody_events", ["request_id"])


def downgrade() -> None:
    op.drop_table("custody_events")
    op.drop_table("evidence_derivations")
    op.drop_table("evidence_sensitive_values")
    op.drop_table("evidence_artifacts")
    op.execute("DROP TYPE IF EXISTS evidence_sensitive_value_kind")
    op.execute("DROP TYPE IF EXISTS evidence_state")
    op.execute("DROP TYPE IF EXISTS evidence_source_class")
