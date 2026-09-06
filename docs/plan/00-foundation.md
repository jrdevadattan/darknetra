# Plan 00 — Foundation: scaffold, config, DB, migrations, CI, contract export

Milestone M0 · Owner A · Depends on nothing · Produces the skeleton every other plan fills.

**Goal.** A running FastAPI service with settings, structured logging, error envelope, async Postgres, Alembic, the base tables (identity, cases, audit, settings), route stubs that already carry the frozen response schemas, an OpenAPI export committed to `docs/openapi.json`, a Makefile, and CI.

**Architecture.** App factory (`create_app()`) registers routers, middleware and lifespan. Domain packages own models and services; `api/v1/routes/*` are thin. `api/v1/schemas/*` are the public Pydantic models (plan 11) and are frozen at M0. A compatibility script fails CI when a path, method, or required response field disappears.

---

## Files to create

```
backend/
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── alembic/
│   ├── env.py                       async engine, target_metadata = Base.metadata
│   ├── script.py.mako
│   └── versions/0001_foundation.py
├── darknetra/
│   ├── __init__.py                  __version__
│   ├── main.py                      create_app(), lifespan
│   ├── config.py                    Settings (pydantic-settings)
│   ├── logging.py                   structlog JSON, request id, PII mask filter
│   ├── db.py                        engine, session factory, Base, mixins, get_session
│   ├── errors.py                    AppError hierarchy + handlers → error envelope
│   ├── deps.py                      common dependencies (settings, session, request id)
│   ├── jobs/runner.py               JobRunner protocol + InProcessRunner (asyncio tasks, bounded)
│   ├── api/v1/router.py             includes all routers
│   ├── api/v1/schemas/              (plan 11) common.py auth.py cases.py evidence.py search.py entities.py analytics.py threads.py findings.py watchlists.py alerts.py reports.py tools.py audit.py admin.py
│   ├── api/v1/routes/               auth.py cases.py evidence.py search.py entities.py analytics.py threads.py findings.py watchlists.py alerts.py reports.py tools.py audit.py admin.py health.py — stubs raise NotImplementedError → 501, except health
│   ├── auth/models.py               User, Session, ApiToken (tables only; logic in plan 01)
│   ├── cases/models.py              Case, CaseMembership
│   ├── audit/models.py              AuditEvent
│   └── settings/models.py           Setting
├── tests/
│   ├── conftest.py                  app + async client + test DB fixtures
│   ├── unit/test_config.py
│   ├── unit/test_errors.py
│   └── integration/test_health.py
└── scripts/
    ├── export_openapi.py            writes docs/openapi.json (sorted keys)
    └── check_openapi_compat.py      compares docs/openapi.json to the live app
Makefile
.github/workflows/ci.yml
.env.example
```

---

## Interfaces

### `config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DARKNETRA_", env_file=".env", extra="ignore")
    env: Literal["development", "test", "production"] = "development"
    build_version: str = "dev"
    database_url: str                                  # postgresql+psycopg://user:pass@host:5432/darknetra
    vault_path: Path = Path("./vault")
    web_origin: str = "http://localhost:3000"
    jwt_signing_key_b64: str                            # exactly 32 random bytes, base64
    field_key_b64: str                                  # AES-256-GCM key for field encryption (plan 01)
    access_ttl_seconds: int = 900
    refresh_ttl_seconds: int = 8 * 3600
    max_upload_bytes: int = 200 * 1024 * 1024
    max_zip_bytes: int = 500 * 1024 * 1024
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    offline_mode: bool = False
    demo_mode: bool = False
    anthropic_api_key: str | None = None
    anthropic_api_key_backup: str | None = None
    case_lead_model: str = "claude-opus-5"
    worker_model: str = "claude-sonnet-5"
    ollama_url: str = "http://127.0.0.1:11434"
    offline_model: str = "qwen3:8b"
    tavily_api_key: str | None = None
    chainalysis_api_key: str | None = None
    trongrid_api_key: str | None = None
    etherscan_api_key: str | None = None
    apify_token: str | None = None
    mcp_gateway_url: str | None = None
    tor_socks_url: str | None = None                    # socks5h://127.0.0.1:9050
    log_level: str = "INFO"
```

`get_settings()` is `lru_cache`d; tests override via `Settings(_env_file=None, ...)`.

### `errors.py`

```python
class AppError(Exception):
    code: str = "INTERNAL"; status: int = 500
    def __init__(self, message: str, *, detail: dict | None = None): ...
class NotFound(AppError): code="NOT_FOUND"; status=404
class Forbidden(AppError): code="FORBIDDEN"; status=403
class Validation(AppError): code="VALIDATION"; status=422
class Conflict(AppError): code="CONFLICT"; status=409
class PolicyDenied(AppError): code="POLICY_DENIED"; status=403
class NetworkRequired(AppError): code="NETWORK_REQUIRED"; status=503
class BudgetExceeded(AppError): code="BUDGET_EXCEEDED"; status=402
class RateLimited(AppError): code="RATE_LIMITED"; status=429      # detail.retry_after_seconds
class Unavailable(AppError): code="UNAVAILABLE"; status=503
```

Handler output: `{"error": {"code": ..., "message": ..., "detail": {...}, "request_id": ...}}`. FastAPI validation errors are mapped to `VALIDATION`. Unhandled exceptions log the traceback and return `INTERNAL` with no internals leaked.

### `db.py`

```python
engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class UUIDPk: id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
class Timestamps: created_at, updated_at (server_default=now(), onupdate)
async def get_session() -> AsyncIterator[AsyncSession]   # dependency; commit on success, rollback on error
```

### `jobs/runner.py`

```python
class JobRunner(Protocol):
    async def submit(self, name: str, coro_factory: Callable[[], Awaitable[None]], *, key: str | None = None) -> str
    async def status(self, job_id: str) -> JobStatus
class InProcessRunner(JobRunner):   # asyncio.Semaphore(4); dedupes by key while running; records status in memory + logs
```

### `logging.py`

structlog with processors: request id (contextvar), timestamp, level, PII mask (regex for emails/phones/API keys → `***`), JSON renderer. `RequestIdMiddleware` sets `X-Request-ID` from header or new uuid.

### `main.py`

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="DARKNETRA API", version=__version__, openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs")
    app.add_middleware(RequestIdMiddleware); CORS(allow_origins=[settings.web_origin], allow_credentials=True)
    register_error_handlers(app); app.include_router(v1_router, prefix="/api/v1")
    lifespan: init engine, verify vault path writable, start scheduler (plan 09 registers), warm embedding model lazily (plan 05)
```

### Health

- `GET /api/v1/health/live` → `{"status":"ok","version":...}`
- `GET /api/v1/health/ready` → `{"status":"ok"|"degraded","checks":{"db":..., "vault":..., "embedding":..., "harness":..., "scheduler":...}}`; 503 when db or vault fail; other checks report `degraded` with reason.

---

## Migration `0001_foundation.py`

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- users, sessions, api_tokens, cases, case_memberships, audit_events, settings  (columns per plan 12)
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events is append-only'; END $$ LANGUAGE plpgsql;
CREATE TRIGGER audit_events_no_update BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
```

Later plans add their tables in their own migrations (plan 12 is the reference for every column).

---

## Route stubs

Every route in plan 11 exists at M0 with its request/response models attached, and returns 501 `{"error":{"code":"NOT_IMPLEMENTED"}}` until its plan lands. This is what makes `docs/openapi.json` complete on day one. Tag routers by area (`auth`, `cases`, `evidence`, …) so the generated TypeScript client is namespaced.

---

## Scripts

- `scripts/export_openapi.py`: `create_app(Settings(_env_file=None, database_url="postgresql+psycopg://x", jwt_signing_key_b64=..., field_key_b64=...))` → `app.openapi()` → write `docs/openapi.json` with sorted keys and 2-space indent.
- `scripts/check_openapi_compat.py --base docs/openapi.json --live`: fails when a path+method disappears, a response schema drops a required property, or an enum loses a member. Additive changes pass. `--allow-breaking` requires bumping `__version__` major.

---

## Makefile

```
dev:        uv sync --all-extras && uv run alembic upgrade head && uv run python scripts/seed_synthetic_case.py --if-missing && uv run uvicorn darknetra.main:app --factory --reload --port 8000
test:       uv run ruff check . && uv run ruff format --check . && uv run mypy darknetra/tools darknetra/capture darknetra/policy && uv run pytest -q
openapi:    uv run python scripts/export_openapi.py && uv run python scripts/check_openapi_compat.py
demo:       uv run python scripts/seed_synthetic_case.py --reset && uv run python scripts/demo_walkthrough.py
migrate:    uv run alembic upgrade head
```

---

## CI (`.github/workflows/ci.yml`)

Jobs: `lint` (ruff, mypy), `test` (services: `pgvector/pgvector:pg16`; env DARKNETRA_DATABASE_URL; `alembic upgrade head`; `pytest`), `contract` (`export_openapi` then `check_openapi_compat` against the committed file; fail on drift). Cache uv. Python 3.12.

---

## Tasks

- [ ] **T1 pyproject + uv**: dependencies per `docs/implementation-plan.md` §4 with extras `ner` (gliner), `embed` (FlagEmbedding), `gnn` (torch, torch-geometric), `dev` (pytest, pytest-asyncio, hypothesis, ruff, mypy, respx, freezegun, testcontainers[postgres]). Pin `python = ">=3.12,<3.13"`. Commit `uv.lock`.
- [ ] **T2 settings + logging**: implement `config.py`, `logging.py`; unit test that a missing `DARKNETRA_JWT_SIGNING_KEY_B64` fails fast and that the PII filter masks `a@b.com` and `+91 98765 43210`.
- [ ] **T3 errors**: hierarchy + handlers; unit test the envelope for each class and for a Pydantic validation error.
- [ ] **T4 db + alembic**: async engine, Base, mixins, `alembic/env.py` (async run_migrations), migration 0001 with extensions, base tables, audit trigger. Integration test: upgrade head on an empty DB; inserting then updating an `audit_events` row raises.
- [ ] **T5 jobs runner**: `InProcessRunner`; unit test dedupe-by-key and bounded concurrency.
- [ ] **T6 app factory + health**: lifespan checks; `/health/live`, `/health/ready`; integration test with DB up and with an unwritable vault path (503).
- [ ] **T7 schemas + stubs**: create every schema module from plan 11 and every route stub returning 501; test that `app.openapi()` contains every path listed in plan 11 (the test holds the list).
- [ ] **T8 scripts + Makefile + CI**: export, compat check, Makefile targets, workflow; commit `docs/openapi.json`.
- [ ] **T9 .env.example**: every variable with a one-line comment; `README` snippet for generating the two 32-byte keys.

## Tests (must pass)

- `tests/unit/test_config.py`, `tests/unit/test_errors.py`, `tests/unit/test_jobs.py`
- `tests/integration/test_health.py`, `tests/integration/test_migrations.py`, `tests/contract/test_openapi_paths.py`

## Acceptance gate

`make dev` boots on an empty database; `GET /api/v1/health/ready` returns 200 with `db` and `vault` ok; `make openapi` writes `docs/openapi.json` containing every path in plan 11; CI green.

## Handoff

Plan 11 and 12 are the references for what T7 and 0001 must contain. Plan 01 starts by filling `auth/` and `cases/` services behind the stubs.
