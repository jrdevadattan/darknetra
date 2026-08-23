from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None
    event_type: str
    resource_type: str
    resource_id: str
    case_id: UUID | None
    request_id: str
    metadata_json: dict[str, Any]
    created_at: datetime


class AuditListResponse(BaseModel):
    items: list[AuditEventRead]
    limit: int
    offset: int
    has_more: bool
