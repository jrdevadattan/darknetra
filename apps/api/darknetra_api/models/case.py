from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra_api.db.base import Base
from darknetra_api.models.enums import CaseSensitivity, CaseStatus
from darknetra_api.models.user import utc_now

CASE_STATUS_ENUM = sa.Enum(CaseStatus, name="case_status")
CASE_SENSITIVITY_ENUM = sa.Enum(CaseSensitivity, name="case_sensitivity")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_code: Mapped[str] = mapped_column(sa.String(40), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(
        CASE_STATUS_ENUM, nullable=False, default=CaseStatus.OPEN, server_default=CaseStatus.OPEN.value
    )
    sensitivity: Mapped[CaseSensitivity] = mapped_column(
        CASE_SENSITIVITY_ENUM,
        nullable=False,
        default=CaseSensitivity.STANDARD,
        server_default=CaseSensitivity.STANDARD.value,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_authority_summary: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
        onupdate=utc_now,
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
