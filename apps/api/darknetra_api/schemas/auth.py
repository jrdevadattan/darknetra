from uuid import UUID

from darknetra_api.models.enums import GlobalRole
from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    new_password: str
    current_password: str | None = None


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str
    global_roles: list[GlobalRole]
    must_change_password: bool


class AuthResponse(BaseModel):
    user: AuthUserResponse
