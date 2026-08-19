# Plan 03 Task 3 — content-addressed Evidence Vault storage verification

- **Verified source:** `1b7003aeffea0157eba1cbf0cbcf708d4240229f`
- **Observed (UTC):** `2026-08-19T13:50:02Z`
- **Runner:** GitHub Actions `ubuntu-latest`

| Gate | Outcome |
|---|---|
| Frozen Python and frontend workspaces | success |
| Alembic upgrade | success |
| Ruff | success |
| Focused Hypothesis/object-store suite | success |
| Complete Python suite | success |
| Frontend lint/typecheck/unit/build | success |
| Base and development Compose validation | success |
| API/worker-only named Evidence Vault volume | success |
| Unprivileged API write and worker read through shared volume | success |
| Real Celery worker ping | success |

The implementation streams originals through random same-filesystem staging, computes SHA-256 during the write, rejects expected-digest mismatches, fsyncs and atomically promotes verified bytes to `sha256/<first2>/<next2>/<digest>`. Duplicate bytes deduplicate; caller filenames never become storage paths; malformed keys and tampered objects fail closed.
