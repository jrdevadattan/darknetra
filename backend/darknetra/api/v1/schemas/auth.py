from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr

from .common import CaseRole, GlobalRole, Schema


class LoginRequest(Schema):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(Schema):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class UserMe(Schema):
    id: UUID
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    global_role: GlobalRole
    must_change_password: bool
    case_roles: dict[str, CaseRole] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list)


TokenScope = Literal[
    "cases:read",
    "evidence:write",
    "threads:run",
    "alerts:read",
    "alerts:handle",
    "monitor:run",
    "reports:generate",
]


class TokenCreate(Schema):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[TokenScope] = Field(min_length=1, max_length=7)
    case_id: UUID | None = None
    expires_in_days: int = Field(30, ge=1, le=365)


class TokenInfo(Schema):
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str]
    case_id: UUID | None = None
    expires_at: datetime
    last_used_at: datetime | None = None


class TokenCreated(TokenInfo):
    token: str
