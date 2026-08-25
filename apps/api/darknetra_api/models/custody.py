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
from darknetra_api.models.evidence import (
    EVIDENCE_SENSITIVE_VALUE_KIND_ENUM,
    EvidenceSensitiveValueKind,
)
from darknetra_api.models.user import utc_now


class CustodyEvent(Base):
    __tablename__ = "custody_events"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["evidence_id", "case_id"],
            ["evidence_artifacts.id", "evidence_artifacts.case_id"],
            ondelete="RESTRICT",
            name="fk_custody_event_artifact_case",
        ),
        sa.CheckConstraint(
            "integrity_sha256 IS NULL OR integrity_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_custody_integrity_sha256_hex",
        ),
        sa.ForeignKeyConstraint(
            ["sensitive_note_id", "evidence_id", "case_id", "sensitive_note_kind"],
            [
                "evidence_sensitive_values.id",
                "evidence_sensitive_values.evidence_id",
                "evidence_sensitive_values.case_id",
                "evidence_sensitive_values.kind",
            ],
            ondelete="RESTRICT",
            name="fk_custody_event_sensitive_note_scope",
        ),
        sa.CheckConstraint(
            "(sensitive_note_id IS NULL AND sensitive_note_kind IS NULL) OR "
            "(sensitive_note_id IS NOT NULL AND sensitive_note_kind = 'CUSTODY_NOTE')",
            name="ck_custody_event_sensitive_note_kind",
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
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    integrity_sha256: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    sensitive_note_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    sensitive_note_kind: Mapped[EvidenceSensitiveValueKind | None] = mapped_column(
        EVIDENCE_SENSITIVE_VALUE_KIND_ENUM,
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=sa.func.now(),
        index=True,
    )

    @staticmethod
    def assert_not_modified(event: CustodyEvent) -> None:
        del event
        raise RuntimeError("custody events are append-only and cannot be updated")


@event.listens_for(CustodyEvent, "before_update")
def _prevent_custody_update(mapper: Mapper[Any], connection: Any, target: CustodyEvent) -> None:
    del mapper, connection
    CustodyEvent.assert_not_modified(target)


@event.listens_for(CustodyEvent, "before_delete")
def _prevent_custody_delete(mapper: Mapper[Any], connection: Any, target: CustodyEvent) -> None:
    del mapper, connection, target
    raise RuntimeError("custody events are append-only and cannot be deleted")
