# Plan 03 Task 1 — durable analysis job boundary verification

- **Verified code commit:** `5bd0f473fee8a7d2279025a18f43eb306e265e42`
- **Observed at (UTC):** `2026-08-18T11:39:00Z`
- **Runner:** GitHub Actions `ubuntu-latest`

| Gate | Outcome |
|---|---|
| Runtime-only test keys | success |
| Reviewed patch application | success |
| `uv lock` + frozen workspace sync | success |
| Alembic upgrade/downgrade/upgrade | success |
| `uv run ruff check .` | success |
| Focused job/Celery tests | success |
| Complete Python regression suite | success |
| Redis restart durability experiment | success |
| Development Compose configuration | success |
| Real Redis/Celery worker health and ping | success |
| Isolated worker-stack teardown | success |

## Verified architecture

- PostgreSQL `jobs` rows are authoritative for `PENDING`, `RUNNING`, `RETRYING`, `SUCCEEDED`, and `FAILED` states.
- Redis is a transient delivery broker only; restarting it removed transient broker data without deleting the persisted job row.
- Celery accepts JSON only, disables pickle, uses bounded task limits, late acknowledgement, worker-loss rejection, one-message prefetch, and explicit publish retry.
- The base Compose topology exposes no Redis host port. The development override binds Redis only to `127.0.0.1`.
- The worker listens only on the `ingest` queue and passed an actual Celery inspect ping.

## Next task

Plan 03 Task 2 may attach jobs to evidence resources while keeping evidence metadata, lineage, custody, and encrypted source fields authoritative in PostgreSQL.
