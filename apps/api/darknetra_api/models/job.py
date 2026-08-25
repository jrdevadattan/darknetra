from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra_api.db.base import Base
from darknetra_api.models.enums import JobStatus
from darknetra_api.models.user import utc_now

JOB_STATUS_ENUM = sa.Enum(JobStatus, name="job_status")


class AnalysisJob(Base):
    """Authoritative state for a job whose broker delivery is transient."""

    __tablename__ = "jobs"
    __table_args__ = (
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempt_count_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    queue: Mapped[str] = mapped_column(
        sa.String(80), nullable=False, default="ingest", server_default="ingest"
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    status: Mapped[JobStatus] = mapped_column(
        JOB_STATUS_ENUM,
        nullable=False,
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.value,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    error_code: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
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
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
