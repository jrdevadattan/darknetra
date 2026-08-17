from typing import Annotated, Literal

from darknetra_api.config import Settings, get_settings
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class LiveHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ComponentHealth(BaseModel):
    name: Literal["api"] = "api"
    status: Literal["ready"] = "ready"


class ReadyHealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    version: str
    components: list[ComponentHealth]


@router.get("/live", response_model=LiveHealthResponse)
def live(settings: Annotated[Settings, Depends(get_settings)]) -> LiveHealthResponse:
    return LiveHealthResponse(version=settings.build_version)


@router.get("/ready", response_model=ReadyHealthResponse)
def ready(settings: Annotated[Settings, Depends(get_settings)]) -> ReadyHealthResponse:
    return ReadyHealthResponse(
        version=settings.build_version,
        components=[ComponentHealth()],
    )
