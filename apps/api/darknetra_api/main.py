import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from darknetra_api.config import Settings, get_settings
from darknetra_api.routers.health import router as health_router
from darknetra_api.routes.admin import router as admin_router
from darknetra_api.routes.audit import router as audit_router
from darknetra_api.routes.auth import router as auth_router
from darknetra_api.routes.cases import router as cases_router
from darknetra_api.routes.evidence import router as evidence_router
from darknetra_api.routes.memberships import router as memberships_router
from darknetra_api.routes.users import router as users_router

StartupSettingsProvider = Callable[[], Settings | Awaitable[Settings]]


async def resolve_startup_settings(provider: StartupSettingsProvider) -> Settings:
    provided = provider()
    settings = await provided if inspect.isawaitable(provided) else provided
    if not isinstance(settings, Settings):
        raise TypeError("startup settings provider must return Settings")
    return settings


def create_app(
    *,
    startup_settings_provider: StartupSettingsProvider,
    web_origin: str,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings = await resolve_startup_settings(startup_settings_provider)
        application.state.sensitive_field_crypto = runtime_settings.require_sensitive_field_crypto()
        try:
            yield
        finally:
            del application.state.sensitive_field_crypto

    application = FastAPI(title="DARKNETRA API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(cases_router, prefix="/api/v1")
    application.include_router(evidence_router, prefix="/api/v1")
    application.include_router(memberships_router, prefix="/api/v1")
    application.include_router(users_router, prefix="/api/v1")
    application.include_router(admin_router, prefix="/api/v1")
    application.include_router(audit_router, prefix="/api/v1")
    return application


def create_production_app() -> FastAPI:
    settings = get_settings()
    return create_app(
        startup_settings_provider=lambda: settings,
        web_origin=settings.web_origin,
    )


app = create_production_app()


__all__ = [
    "StartupSettingsProvider",
    "app",
    "create_app",
    "create_production_app",
    "resolve_startup_settings",
]
