from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.models.audit import AuditEvent


def append_audit_event(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    event_type: str,
    resource_type: str,
    resource_id: str,
    request_id: str,
    case_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        case_id=case_id,
        request_id=request_id,
        metadata_json=metadata or {},
    )
    session.add(event)
    return event
