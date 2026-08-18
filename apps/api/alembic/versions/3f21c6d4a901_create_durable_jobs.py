"""create durable jobs

Revision ID: 3f21c6d4a901
Revises: 670002e45670
Create Date: 2026-08-18 10:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f21c6d4a901"
down_revision: str | Sequence[str] | None = "670002e45670"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    job_state = sa.Enum("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "RETRYING", name="job_state")
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=True),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=120), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("queue", sa.String(length=80), server_default="ingest", nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("state", job_state, server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count_nonnegative"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_jobs_case_id"), "jobs", ["case_id"], unique=False)
    op.create_index(op.f("ix_jobs_state"), "jobs", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_state"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_case_id"), table_name="jobs")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS job_state")
