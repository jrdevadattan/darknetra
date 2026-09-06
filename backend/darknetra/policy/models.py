"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid()
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    allow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    args_hash: Mapped[str] = mapped_column(Text, nullable=False)
    requester_kind: Mapped[str] = mapped_column(Text, nullable=False)
    requester_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("case_id", "id"),
        CheckConstraint(
            "requester_kind IN ('USER', 'THREAD', 'WATCHLIST_ITEM', 'SYSTEM')",
            name="requester_kind",
        ),
    )
