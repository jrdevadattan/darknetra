from datetime import datetime
from typing import Any
from uuid import UUID

from .common import ActorRef, Schema


class AuditEvent(Schema):
    id: UUID
    at: datetime
    actor: ActorRef
    case_id: UUID | None = None
    thread_id: UUID | None = None
    action: str
    target_type: str | None = None
    target_id: UUID | None = None
    detail: dict[str, Any]
    result_hash: str | None = None
    request_id: str | None = None
