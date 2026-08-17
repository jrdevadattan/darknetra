from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra_api.db.base import Base
from darknetra_api.models.enums import GlobalRole


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


GLOBAL_ROLE_ENUM = sa.Enum(GlobalRole, name="global_role")


class User(Base):
    """Investigator identity. UUID4 is used until an approved UUIDv7 dependency is adopted."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    username_normalized: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    global_roles: Mapped[list[GlobalRole]] = mapped_column(
        ARRAY(GLOBAL_ROLE_ENUM), nullable=False, default=list, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True, server_default=sa.true())
    must_change_password: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    failed_login_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
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
