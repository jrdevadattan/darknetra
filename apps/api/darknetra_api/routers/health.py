from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from darknetra_api.config import Settings, get_settings

router = APIRouter(prefix="/health", tags=["health"])


class LiveHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str


class ComponentHealth(BaseModel):
    name: Literal["api", "sensitive-field-crypto"]
    status: Literal["ready"] = "ready"


class ReadyHealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    version: str
    components: list[ComponentHealth]


@router.get("/live", response_model=LiveHealthResponse)
def live(settings: Annotated[Settings, Depends(get_settings)]) -> LiveHealthResponse:
    return LiveHealthResponse(version=settings.build_version)


@router.get("/ready", response_model=ReadyHealthResponse)
def ready(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadyHealthResponse:
    if getattr(request.app.state, "sensitive_field_crypto", None) is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="sensitive field cryptography is not ready",
        )
    return ReadyHealthResponse(
        version=settings.build_version,
        components=[
            ComponentHealth(name="api"),
            ComponentHealth(name="sensitive-field-crypto"),
        ],
    )
