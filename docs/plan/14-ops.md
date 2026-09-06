# Plan 14 — Ops: environment, compose, native setup, health, logging, backups, demo-day runbook

Cross-cutting · Owner A. The team installs its own tooling; this plan fixes what the software expects.

---

## Environment variables (`.env.example`)

```
# Core
DARKNETRA_ENV=development                 # development | test | production
DARKNETRA_BUILD_VERSION=dev
DARKNETRA_DATABASE_URL=postgresql+psycopg://darknetra:darknetra@127.0.0.1:5432/darknetra
DARKNETRA_VAULT_PATH=./vault
DARKNETRA_WEB_ORIGIN=http://localhost:3000
DARKNETRA_JWT_SIGNING_KEY_B64=            # python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"
DARKNETRA_FIELD_KEY_B64=                  # same generator; different value
DARKNETRA_LOG_LEVEL=INFO
DARKNETRA_MAX_UPLOAD_BYTES=209715200
DARKNETRA_MAX_ZIP_BYTES=524288000

# Models and harnesses
ANTHROPIC_API_KEY=                        # Claude harness, vision transcription, narrative, triage
ANTHROPIC_API_KEY_BACKUP=
DARKNETRA_CASE_LEAD_MODEL=claude-opus-5
DARKNETRA_WORKER_MODEL=claude-sonnet-5
DARKNETRA_EMBEDDING_MODEL=BAAI/bge-m3     # or intfloat/multilingual-e5-small (set DARKNETRA_EMBEDDING_DIM=384 and reindex)
DARKNETRA_EMBEDDING_DIM=1024
DARKNETRA_OLLAMA_URL=http://127.0.0.1:11434
DARKNETRA_OFFLINE_MODEL=qwen3:8b
DARKNETRA_OFFLINE_MODE=false
DARKNETRA_DEMO_MODE=false
DARKNETRA_TRIAGE_MODEL_ENABLED=true

# OSINT and chain
TAVILY_API_KEY=
CHAINALYSIS_API_KEY=
TRONGRID_API_KEY=
ETHERSCAN_API_KEY=
APIFY_TOKEN=
DARKNETRA_APIFY_TELEGRAM_ACTOR=            # actor id for public channel posts
DARKNETRA_MCP_GATEWAY_URL=                 # http://127.0.0.1:8811/mcp (Docker MCP gateway) or supergateway URL
DARKNETRA_TOR_SOCKS_URL=                   # socks5h://127.0.0.1:9050 (collector profile only)

# Bootstrap (used once by the CLI, never by the app)
DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD=
DARKNETRA_DEMO_ANALYST_PASSWORD=
```

Rules: the app fails fast on missing required keys; no defaults for secrets; `NEXT_PUBLIC_*` never contains secrets (frontend); keys for reach services are optional and their tools show `health: disabled` when absent.

---

## Postgres

- Version 16 with `vector` and `pg_trgm` extensions available to the app role.
- Roles: `darknetra_migrate` (owner, runs Alembic) and `darknetra_app` (runtime). Grant matrix for `darknetra_app`: SELECT/INSERT/UPDATE on all tables; **no DELETE** on `evidence`, `custody_events`, `derivatives`, `decisions`, `audit_events`, `reports`, `findings`; DELETE allowed on `chunks` (reindex), `rate_counters`, `run_events` (retention), `replay_entries`, `monitor_seen_urls`.
- Settings: `shared_buffers` ≥ 512 MB, `maintenance_work_mem` ≥ 256 MB for HNSW builds, `max_connections` ≥ 50.
- Native install on Windows/macOS/Linux or Docker (`pgvector/pgvector:pg16`) are both fine; the app only needs the URL.

## Docker Compose (`infra/docker-compose.yml`)

Profiles: default (`postgres`), `offline` (`ollama` with the model pulled at build), `collector` (`tor` exposing SOCKS 9050 only to the `collector` network; the API joins that network only when `DARKNETRA_TOR_SOCKS_URL` is set), `osint` (`mcp-gateway` running `darknet-mcp-server` and `osint-tools-mcp-server` behind Docker's MCP gateway or `supergateway --outputTransport streamableHttp`), `api` (the backend image, non-root, healthcheck on `/health/live`). Volumes: `pgdata`, `vault`, `models` (bge-m3, GLiNER, GNN artefacts pre-downloaded by `scripts/fetch_models.py`).

---

## Health, logging, metrics

- `/health/live`: process up. `/health/ready`: db (SELECT 1), vault (write/delete temp file), embedding (model loaded or `degraded: lexical only`), harness (`claude` CLI present + key, or `ollama` reachable; else `degraded: offline`), scheduler (running), gateway (optional; `disabled` when unset), tor (optional).
- Logs: JSON lines to stdout; fields `ts, level, logger, request_id, run_id, case_id, actor, event, duration_ms`; PII mask filter; never log tool args containing locators unredacted (adapters redact to domain).
- Metrics (minimal, `/metrics` Prometheus text): request latency histogram, runs by status, tool calls by tool/status, captures by source class, alerts by kind, scheduler lag (oldest overdue item seconds), embedding queue size. Langfuse tracing arrives in plan 16.

---

## Backups

- `scripts/backup.py` nightly (cron on the host): `pg_dump -Fc` + vault tar + manifest with hashes; keep 7 daily.
- `scripts/restore.py` verifies every evidence hash after restore; a mismatch fails loudly.
- Before the finale: full backup on two laptops and a USB drive.

---

## Demo-day runbook (Tue 8 → Wed 9 Sep)

1. **H+0** on each laptop: `git pull`, `uv sync`, `make migrate`, `make dev`; `/health/ready` recorded. Decide online vs offline for the primary laptop by testing `claude --version` and one API call; set `DARKNETRA_OFFLINE_MODE` accordingly on the backup laptop.
2. Seed: `scripts/seed_synthetic_case.py --reset`; confirm `seed_result.json`; `/tools` health probe; note which lanes are unavailable (expect Tor).
3. Warm the replay cache: run the six demo questions once with `DARKNETRA_DEMO_MODE=true`.
4. Before the pitch: `make demo` end to end; restart the API; check `/health/ready`; open the frontend; keep the backup video on the second laptop.
5. Failure recovery: API crash → `make dev` (state is in Postgres and the vault); model stall → switch the thread's harness to OFFLINE via `PATCH /threads/{id}` or rely on replay; network loss → `PATCH /admin/settings {offline_mode:true}`; database trouble → restore from the morning backup into a fresh database and re-point the URL.
6. After the finale: `scripts/backup.py`; export the audit log (`GET /audit`) for the write-up.
