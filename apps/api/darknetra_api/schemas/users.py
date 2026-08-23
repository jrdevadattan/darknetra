from uuid import UUID

from darknetra_api.models.enums import GlobalRole
from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str
    is_active: bool
    global_roles: list[GlobalRole]


class UserListResponse(BaseModel):
    items: list[UserRead]
