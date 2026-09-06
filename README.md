# DARKNETRA backend

An evidence-first case workspace built with FastAPI, Python 3.12, PostgreSQL 16 and pgvector. The backend consumes the plans in `docs/plan/`; the Next.js frontend is a separate track.

## Start locally

Install `uv` and start Docker Desktop's Linux engine. From this directory:

```powershell
uv run --project backend python scripts/manage.py dev
```

This generates a private `.env` when absent, builds the API image, starts PostgreSQL, applies migrations, creates the initial administrator, changes its bootstrap password through the API, and uploads the SYN-CHD-001 synthetic fixture. Repeating it preserves credentials and case evidence.

API documentation: <http://127.0.0.1:8000/api/v1/docs>. Readiness: <http://127.0.0.1:8000/api/v1/health/ready>.

The administrator username is `administrator`; its password is `DARKNETRA_ADMIN_PASSWORD` in your local `.env`. The fixture account is `analyst.demo` with `DARKNETRA_DEMO_ANALYST_PASSWORD`. These credentials are randomly generated, never checked in or printed by the scripts.

The default mode is explicitly deterministic and offline. It quotes captured evidence and reports missing models and external services as unavailable. Readiness is `degraded` while those optional services are absent; database and vault failures return HTTP 503.

## Development commands

Use `make <command>` where Make is installed, or the Windows-compatible equivalent:

```powershell
uv run --project backend python scripts/manage.py test
uv run --project backend python scripts/manage.py demo
uv run --project backend python scripts/manage.py openapi
uv run --project backend python scripts/manage.py stop
```

`test` migrates the dedicated `darknetra_test` database, then runs Ruff lint/format checks, strict mypy on tools/capture/policy, and pytest. PostgreSQL must be running. `demo` exercises evidence, cited SSE answers, correlation, synthetic analyst decisions, the graph, wallet availability, monitoring alerts and reports over HTTP. `stop` preserves volumes. `up` starts the stack without seeding.

For host-based development, use `migrate`, `bootstrap` and `serve` commands; stop the Docker API first to free port 8000. Use only one API process per database: jobs and the scheduler run in-process. Restart marks interrupted runs/reports as errors and interrupted evidence processing as an audited FAILED state that can be reprocessed. Original bytes remain intact. A durable external worker is a later deployment concern.

```powershell
uv run --project backend python backend/scripts/run_retrieval_eval.py
```

This runs the synthetic retrieval evaluation. Generated fixtures, evaluation output, vault data, `.env` and backups are ignored by Git. The exported contract at `docs/openapi.json` is tracked.

## API conventions

All application routes start with `/api/v1`. Browser sessions use HttpOnly access/refresh cookies plus a readable CSRF cookie. Mutations require `X-CSRF-Token` and the configured `Origin` (`http://localhost:3000` by default). Service tokens use `Authorization: Bearer dk_...` with explicit scopes and optional case binding. Mixing cookie and bearer authentication is rejected. The walkthrough is a working HTTP client example.

Evidence codes are local to each case. Case access checks apply before resolving evidence, entities, threads, decisions, alerts and reports. Unknown and inaccessible cases both return 404. Original evidence, custody, audit and decisions cannot be deleted; report regeneration appends a new version. Finalized reports cannot be changed.

`docs/implementation-plan.md` is the design reference. `docs/build-progress.md` records the implemented scope, verification and remaining gaps. Errors use the stable envelope documented in the exported API contract. `/api/v1/metrics` provides aggregate Prometheus metrics to authenticated administrators. The `/metrics` alias requires explicitly supplied authentication because access cookies are restricted to `/api`.

## Configuration and optional providers

Chat uses a custom Python runtime with interchangeable Claude Agent SDK, Ollama and deterministic quotation adapters. It does not use LangChain or LangGraph. Threads, messages, tool calls and SSE event sequences persist in PostgreSQL. Each model adapter receives bounded conversation and attachment/pinned-finding context, uses the shared typed tool registry and policy/capture boundary, and returns answers through the claim checker. Replay keys include conversation context and current case state. NVIDIA NIM is compatible with this adapter design, but a NIM/OpenAI-compatible adapter is not implemented in this build.

Every setting is listed in `.env.example`. Settings and API keys use the `DARKNETRA_` prefix. Docker replaces the database and vault addresses with its internal addresses; host scripts use loopback port 55432. The API uses the restricted `darknetra_app` role; only migrations use `darknetra_migrate`.

The offline profile can start Ollama:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml --profile offline up -d ollama
```

Ollama model weights must be installed separately. Claude and Ollama adapters are present, but live provider acceptance requires configured credentials/models. The repository does not contain trained GNN, sanctions lists, dense embedding or NER weights. Their absence must not be interpreted as a clean wallet screen or a negative finding. Public source collectors run through the policy/capture gate; Tor, person-lookup and unsupported adapters remain unavailable. No real target data is used by the fixture or demo.

## Backup and restore

```powershell
uv run --project backend python scripts/backup.py
uv run --project backend python scripts/restore.py backups/<backup-name> --database darknetra_restore_rehearsal --vault backups/restored-vault
```

Backups contain a PostgreSQL custom dump, the immutable vault and a SHA-256 manifest. Restore verifies the backup, creates a fresh database and a new vault directory, then rehashes every referenced original, derivative and report artifact. Existing targets are refused. Back up the encryption/signing keys separately in an appropriate secret store: the backup intentionally does not copy `.env`.

Keep backups on storage appropriate for the case data. The scripts preserve all backup versions; choose a retention schedule for deployment. The Compose stack is a local development installation bound to loopback, not a production deployment.
