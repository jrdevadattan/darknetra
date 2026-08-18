"""create evidence provenance schema

Revision ID: 8a7f2d91c402
Revises: 3f21c6d4a901
Create Date: 2026-08-18 18:50:00.000000
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
    source_class.create(op.get_bind(), checkfirst=True)
    state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "evidence_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("source_class", source_class, nullable=False),
        sa.Column("source_type", sa.String(length=120), nullable=False),
        sa.Column("source_locator_ciphertext", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_locator_hash", sa.String(length=64), nullable=True),
        sa.Column("authority_reference_ciphertext", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acquisition_method", sa.String(length=160), nullable=False),
        sa.Column("collector_user_id", sa.UUID(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_timezone", sa.String(length=80), nullable=True),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("sha512", sa.String(length=128), nullable=True),
        sa.Column("object_key", sa.String(length=180), nullable=True),
        sa.Column("state", state, server_default="STAGING", nullable=False),
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column("tool_version", sa.String(length=80), nullable=True),
        sa.Column("notes_ciphertext", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_evidence_size_nonnegative"),
        sa.CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="ck_evidence_sha256_hex"),
        sa.CheckConstraint("sha512 IS NULL OR sha512 ~ '^[0-9a-f]{128}$'", name="ck_evidence_sha512_hex"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collector_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_artifacts_case_id"), "evidence_artifacts", ["case_id"], unique=False)
    op.create_index(op.f("ix_evidence_artifacts_collector_user_id"), "evidence_artifacts", ["collector_user_id"], unique=False)
    op.create_index(op.f("ix_evidence_artifacts_sha256"), "evidence_artifacts", ["sha256"], unique=False)
    op.create_index(op.f("ix_evidence_artifacts_source_locator_hash"), "evidence_artifacts", ["source_locator_hash"], unique=False)
    op.create_index(op.f("ix_evidence_artifacts_state"), "evidence_artifacts", ["state"], unique=False)

    op.create_table(
        "evidence_derivations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("parent_evidence_id", sa.UUID(), nullable=False),
        sa.Column("child_evidence_id", sa.UUID(), nullable=False),
        sa.Column("transformation", sa.String(length=120), nullable=False),
        sa.Column("transformer_version", sa.String(length=80), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("parent_evidence_id <> child_evidence_id", name="ck_evidence_derivation_not_self"),
        sa.ForeignKeyConstraint(["child_evidence_id"], ["evidence_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_evidence_id"], ["evidence_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_evidence_id", "child_evidence_id", "transformation", "transformer_version", name="uq_evidence_derivation_identity"),
    )
    op.create_index(op.f("ix_evidence_derivations_child_evidence_id"), "evidence_derivations", ["child_evidence_id"], unique=False)
    op.create_index(op.f("ix_evidence_derivations_parent_evidence_id"), "evidence_derivations", ["parent_evidence_id"], unique=False)

    op.create_table(
        "custody_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_custody_events_actor_user_id"), "custody_events", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_custody_events_case_id"), "custody_events", ["case_id"], unique=False)
    op.create_index(op.f("ix_custody_events_created_at"), "custody_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_custody_events_event_type"), "custody_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_custody_events_evidence_id"), "custody_events", ["evidence_id"], unique=False)
    op.create_index(op.f("ix_custody_events_request_id"), "custody_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_table("custody_events")
    op.drop_table("evidence_derivations")
    op.drop_table("evidence_artifacts")
    op.execute("DROP TYPE IF EXISTS evidence_state")
    op.execute("DROP TYPE IF EXISTS evidence_source_class")
