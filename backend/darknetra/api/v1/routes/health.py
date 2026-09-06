import tempfile
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from darknetra import __version__
from darknetra.api.v1.schemas.admin import Health, HealthCheck, LiveHealth

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LiveHealth)
async def live():
    return LiveHealth(version=__version__)


@router.get("/health/ready", response_model=Health)
async def ready(request: Request, response: Response):
    checks = {}
    try:
        async with request.app.state.session_factory() as db:
            await db.execute(text("SELECT 1"))
            applied = set((await db.scalars(text("SELECT version_num FROM alembic_version"))).all())
            expected = set(
                ScriptDirectory(str(Path(__file__).resolve().parents[4] / "alembic")).get_heads()
            )
            if applied != expected:
                raise RuntimeError("Migrations are out of date")
        checks["db"] = HealthCheck(status="ok")
    except Exception:
        checks["db"] = HealthCheck(status="failed", message="Database or migrations unavailable")
    try:
        directory = Path(request.app.state.settings.vault_path)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b"readiness")
        checks["vault"] = HealthCheck(status="ok")
    except OSError:
        checks["vault"] = HealthCheck(status="failed", message="Vault is not writable")
    checks["embedding"] = HealthCheck(
        status="degraded", message="Lexical retrieval available; embedding model is not loaded"
    )
    mode = request.app.state.settings.harness_mode
    checks["harness"] = HealthCheck(
        status="degraded",
        message="Explicit deterministic evidence-quote mode"
        if mode == "deterministic"
        else "Provider readiness is checked before each run",
    )
    scheduler = getattr(request.app.state, "scheduler", None)
    checks["scheduler"] = HealthCheck(
        status="ok" if scheduler and scheduler.running else "disabled",
        message=None if scheduler else "Scheduler disabled",
    )
    checks["collector"] = HealthCheck(
        status="disabled", message="Isolated collector is not configured"
    )
    if checks["db"].status == "failed" or checks["vault"].status == "failed":
        response.status_code = 503
    return Health(
        status="degraded" if any(c.status != "ok" for c in checks.values()) else "ok",
        version=__version__,
        checks=checks,
    )
