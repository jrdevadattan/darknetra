from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from darknetra_api.db.base import Base
from darknetra_api.models.user import utc_now


class CustodyEvent(Base):
    __tablename__ = "custody_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("evidence_artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now(), index=True
    )


@event.listens_for(CustodyEvent, "before_update")
def _prevent_custody_update(mapper: Mapper[Any], connection: Any, target: CustodyEvent) -> None:
    del mapper, connection, target
    raise RuntimeError("custody events are append-only and cannot be updated")


@event.listens_for(CustodyEvent, "before_delete")
def _prevent_custody_delete(mapper: Mapper[Any], connection: Any, target: CustodyEvent) -> None:
    del mapper, connection, target
    raise RuntimeError("custody events are append-only and cannot be deleted")
