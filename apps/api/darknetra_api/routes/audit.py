from datetime import datetime
from typing import Annotated
from uuid import UUID

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import ROLE_PERMISSIONS
from darknetra_api.dependencies.auth import DbSession, require_global_permission
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.schemas.audit import AuditListResponse
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

router = APIRouter(prefix="/audit", tags=["audit"])
AuditReader = Annotated[User, Depends(require_global_permission(Permission.AUDIT_READ))]


def _has_global_audit_scope(user: User) -> bool:
    return GlobalRole.ADMIN in user.global_roles or GlobalRole.AUDITOR in user.global_roles


def _case_scoped_audit_roles(user: User) -> list[GlobalRole]:
    return [
        role
        for role in user.global_roles
        if role not in {GlobalRole.ADMIN, GlobalRole.AUDITOR}
        and Permission.AUDIT_READ in ROLE_PERMISSIONS.get(role, frozenset())
    ]


@router.get("", response_model=AuditListResponse)
async def list_audit_events_route(
    db: DbSession,
    user: AuditReader,
    case_id: UUID | None = None,
    resource_type: str | None = None,
    event_type: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditListResponse:
    statement = select(AuditEvent)

    if not _has_global_audit_scope(user):
        auditable_roles = _case_scoped_audit_roles(user)
        if not auditable_roles:
            return AuditListResponse(items=[], limit=limit, offset=offset, has_more=False)
        visible_case_ids = (
            select(CaseMembership.case_id)
            .join(
                CaseMembershipRole,
                CaseMembershipRole.membership_id == CaseMembership.id,
            )
            .where(
                CaseMembership.user_id == user.id,
                CaseMembershipRole.role.in_(auditable_roles),
            )
            .distinct()
        )
        statement = statement.where(AuditEvent.case_id.in_(visible_case_ids))

    if case_id is not None:
        statement = statement.where(AuditEvent.case_id == case_id)
    if resource_type is not None:
        statement = statement.where(AuditEvent.resource_type == resource_type)
    if event_type is not None:
        statement = statement.where(AuditEvent.event_type == event_type)
    if from_time is not None:
        statement = statement.where(AuditEvent.created_at >= from_time)
    if to_time is not None:
        statement = statement.where(AuditEvent.created_at <= to_time)

    statement = (
        statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list((await db.scalars(statement)).all())
    return AuditListResponse(
        items=rows[:limit],
        limit=limit,
        offset=offset,
        has_more=len(rows) > limit,
    )
