from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from darknetra_api.config import get_settings
from darknetra_api.routers.health import router as health_router
from darknetra_api.routes.admin import router as admin_router
from darknetra_api.routes.audit import router as audit_router
from darknetra_api.routes.auth import router as auth_router
from darknetra_api.routes.cases import router as cases_router
from darknetra_api.routes.memberships import router as memberships_router
from darknetra_api.routes.users import router as users_router

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings_provider = application.dependency_overrides.get(get_settings, get_settings)
    runtime_settings = settings_provider()
    application.state.sensitive_field_crypto = runtime_settings.require_sensitive_field_crypto()
    try:
        yield
    finally:
        del application.state.sensitive_field_crypto


app = FastAPI(title="DARKNETRA API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
)
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(cases_router, prefix="/api/v1")
app.include_router(memberships_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
