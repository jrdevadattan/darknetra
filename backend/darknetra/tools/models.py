"""Persisted domain records. Database checks preserve provenance and case boundaries."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from darknetra.db import Base


class ToolRegistry(Base):
    __tablename__ = "tool_registry"
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    server: Mapped[str | None] = mapped_column(Text, nullable=True)
    lane: Mapped[str] = mapped_column(Text, nullable=False)
    requires_network: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    rate_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    rate_cap_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "source_class IN ('SYNTHETIC', 'SEIZED', 'UPLOAD', 'OSINT_SURFACE', 'OSINT_DARK', 'CHAIN', 'TELEGRAM', 'REPORT')",
            name="source_class",
        ),
    )
