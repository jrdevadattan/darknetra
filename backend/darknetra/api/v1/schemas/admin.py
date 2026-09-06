from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr

from .common import GlobalRole, Schema


class Settings(Schema):
    demo_mode: bool
    offline_mode: bool
    monitor_interval_override: int | None = None
    banner: str | None = None
    embedding_model: str
    case_lead_model: str
    worker_model: str
    offline_model: str


class SettingsPatch(Schema):
    demo_mode: bool | None = None
    offline_mode: bool | None = None
    monitor_interval_override: int | None = Field(None, gt=0)
    case_lead_model: str | None = Field(None, min_length=1, max_length=200)
    worker_model: str | None = Field(None, min_length=1, max_length=200)
    offline_model: str | None = Field(None, min_length=1, max_length=200)


class UserCreate(Schema):
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    global_role: GlobalRole
    is_active: bool = True
    password: SecretStr = Field(min_length=12, max_length=1024)


class UserPatch(Schema):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    global_role: GlobalRole | None = None
    is_active: bool | None = None


class User(Schema):
    id: UUID
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    global_role: GlobalRole
    is_active: bool
    must_change_password: bool


class HealthCheck(Schema):
    status: str
    message: str | None = None


class Health(Schema):
    status: Literal["ok", "degraded"]
    version: str
    checks: dict[str, HealthCheck]


class LiveHealth(Schema):
    status: Literal["ok"] = "ok"
    version: str
