import importlib
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

import darknetra.models  # noqa: F401
from darknetra import __version__
from darknetra.api.middleware import RequestSizeLimit
from darknetra.api.v1.schemas.common import ErrorEnvelope
from darknetra.config import Settings
from darknetra.db import build_engine, build_session_factory
from darknetra.errors import register_error_handlers
from darknetra.jobs.runner import InProcessRunner
from darknetra.logging import RequestIdMiddleware, configure_logging
from darknetra.metrics import install_metrics
from darknetra.settings.models import Setting


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        settings = Settings(_env_file=env_path if env_path.exists() else ".env")
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app):
        engine = build_engine(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        app.state.jobs = InProcessRunner()
        app.state.scheduler = None
        try:
            async with app.state.session_factory() as db:
                for setting in (await db.scalars(select(Setting))).all():
                    if setting.key in {
                        "demo_mode",
                        "offline_mode",
                        "monitor_interval_override",
                        "case_lead_model",
                        "worker_model",
                        "offline_model",
                    }:
                        setattr(settings, setting.key, setting.value)
        except Exception:
            # Liveness remains available; readiness reports a missing/misconfigured database.
            pass
        if settings.env != "test":
            from datetime import UTC, datetime

            from darknetra.agent.service import recover_interrupted_runs
            from darknetra.cases.models import Case
            from darknetra.ingest.recovery import recover_interrupted_evidence
            from darknetra.reports.service import recover_interrupted_reports

            try:
                await recover_interrupted_runs(app)
                await recover_interrupted_reports(app)
                recovery_before = datetime.now(UTC)
                async with app.state.session_factory() as db:
                    case_ids = list(await db.scalars(select(Case.id)))
                for case_id in case_ids:
                    async with app.state.session_factory() as db:
                        await recover_interrupted_evidence(db, case_id, before=recovery_before)
                        await db.commit()
            except Exception:
                # Readiness still reports database failures; do not fabricate recovery.
                import structlog

                structlog.get_logger().error("startup_recovery_unavailable")
        if settings.scheduler_enabled:
            scheduler = AsyncIOScheduler(timezone="UTC")
            app.state.scheduler = scheduler
            module = "darknetra.monitor.scheduler"
            if importlib.util.find_spec(module):
                importlib.import_module(module).configure(app, scheduler)
            scheduler.start()
        try:
            yield
        finally:
            if app.state.scheduler and app.state.scheduler.running:
                app.state.scheduler.shutdown(wait=False)
            await app.state.jobs.shutdown()
            await engine.dispose()

    app = FastAPI(
        title="DARKNETRA API",
        version=__version__,
        lifespan=lifespan,
        responses={
            code: {"model": ErrorEnvelope}
            for code in (401, 402, 403, 404, 409, 413, 422, 423, 429, 500, 503)
        },
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )
    app.state.settings = settings
    register_error_handlers(app)
    install_metrics(app)
    for name in (
        "auth",
        "cases",
        "evidence",
        "search",
        "entities",
        "taxonomy",
        "analytics",
        "threads",
        "findings",
        "watchlists",
        "alerts",
        "reports",
        "tools",
        "admin",
        "health",
    ):
        module = "darknetra.api.v1.routes." + name
        if importlib.util.find_spec(module):
            app.include_router(importlib.import_module(module).router, prefix="/api/v1")
    app.add_middleware(RequestSizeLimit, max_bytes=settings.max_upload_bytes + 2 * 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "X-Request-ID",
            "Authorization",
            "Last-Event-ID",
            "If-Match",
        ],
        expose_headers=["X-Request-ID", "Retry-After", "ETag"],
    )
    app.add_middleware(RequestIdMiddleware)
    return app
