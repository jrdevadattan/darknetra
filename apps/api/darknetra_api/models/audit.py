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


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    case_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now(), index=True
    )


@event.listens_for(AuditEvent, "before_update")
def _prevent_audit_update(mapper: Mapper[Any], connection: Any, target: AuditEvent) -> None:
    del mapper, connection, target
    raise RuntimeError("audit events are append-only and cannot be updated")


@event.listens_for(AuditEvent, "before_delete")
def _prevent_audit_delete(mapper: Mapper[Any], connection: Any, target: AuditEvent) -> None:
    del mapper, connection, target
    raise RuntimeError("audit events are append-only and cannot be deleted")
