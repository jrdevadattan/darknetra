from datetime import datetime
from uuid import UUID

from darknetra_api.models.enums import GlobalRole
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MembershipCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    roles: set[GlobalRole] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def reject_admin_role(cls, roles: set[GlobalRole]) -> set[GlobalRole]:
        if GlobalRole.ADMIN in roles:
            raise ValueError("ADMIN cannot be assigned as a case membership role")
        return roles


class MembershipUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: set[GlobalRole] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def reject_admin_role(cls, roles: set[GlobalRole]) -> set[GlobalRole]:
        if GlobalRole.ADMIN in roles:
            raise ValueError("ADMIN cannot be assigned as a case membership role")
        return roles


class MembershipResponse(BaseModel):
    user_id: UUID
    username: str
    display_name: str
    roles: list[GlobalRole]
    created_at: datetime


class MembershipListResponse(BaseModel):
    items: list[MembershipResponse]
