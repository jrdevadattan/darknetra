from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from darknetra_api.db.base import Base
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import GLOBAL_ROLE_ENUM, utc_now


class CaseMembership(Base):
    __tablename__ = "case_memberships"
    __table_args__ = (
        sa.UniqueConstraint("case_id", "user_id", name="uq_case_memberships_case_user"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=utc_now, server_default=sa.func.now()
    )


class CaseMembershipRole(Base):
    __tablename__ = "case_membership_roles"
    __table_args__ = (
        sa.CheckConstraint("role <> 'ADMIN'", name="ck_case_membership_role_not_admin"),
    )

    membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("case_memberships.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[GlobalRole] = mapped_column(GLOBAL_ROLE_ENUM, primary_key=True)
