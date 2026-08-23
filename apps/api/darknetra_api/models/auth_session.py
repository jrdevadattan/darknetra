from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra_api.db.base import Base
from darknetra_api.models.user import utc_now


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    remote_context_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
