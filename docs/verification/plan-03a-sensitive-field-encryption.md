# Plan 03a — sensitive-field encryption verification

- **Verified commit:** `f9d6d942ea871f373422b1494dbe95dbde0abfb7`
- **Observed at (UTC):** `2026-08-18T10:15:31Z`
- **Runner:** GitHub Actions `ubuntu-latest`

| Gate | Outcome |
|---|---|
| Runtime-only v1/v2/JWT/blind keys | success |
| README + architecture preflight | success |
| Locked workspace installation | success |
| Disposable PostgreSQL migration | success |
| Active-v2 runtime probe | success |
| `uv run ruff check .` | success |
| `uv run pytest -q` | success |
| Authentication/case regression | success |
| Tracked-secret scan | success |
| Docker Compose configuration | success |
| Docker API/web smoke | success |

## Python suite
```text
........................................................................ [ 80%]
.................                                                        [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
89 passed, 1 warning in 9.80s
```

## Authentication and case regression
```text
................                                                         [100%]
16 passed in 2.95s
```

## Secret scan
```text
No committed sensitive-field key literal detected.
```

## Docker smoke
```text

#37 [web] resolving provenance for metadata file
#37 DONE 0.0s
 api  Built
 web  Built
 Network darknetra_app  Creating
 Network darknetra_app  Created
 Volume "darknetra_postgres-data"  Creating
 Volume "darknetra_postgres-data"  Created
 Container darknetra-postgres-1  Creating
 Container darknetra-postgres-1  Created
 Container darknetra-api-1  Creating
 Container darknetra-api-1  Created
 Container darknetra-web-1  Creating
 Container darknetra-web-1  Created
 Container darknetra-postgres-1  Starting
 Container darknetra-postgres-1  Started
 Container darknetra-postgres-1  Waiting
 Container darknetra-postgres-1  Healthy
 Container darknetra-api-1  Starting
 Container darknetra-api-1  Started
 Container darknetra-api-1  Waiting
 Container darknetra-api-1  Healthy
 Container darknetra-web-1  Starting
 Container darknetra-web-1  Started
 Container darknetra-postgres-1  Waiting
 Container darknetra-api-1  Waiting
 Container darknetra-web-1  Waiting
 Container darknetra-web-1  Healthy
 Container darknetra-api-1  Healthy
 Container darknetra-postgres-1  Healthy
NAME                   IMAGE           COMMAND                  SERVICE    CREATED          STATUS                    PORTS
darknetra-api-1        darknetra-api   "uv run --no-sync uv…"   api        12 seconds ago   Up 6 seconds (healthy)    127.0.0.1:8000->8000/tcp
darknetra-postgres-1   postgres:18     "docker-entrypoint.s…"   postgres   12 seconds ago   Up 12 seconds (healthy)   127.0.0.1:5432->5432/tcp
darknetra-web-1        darknetra-web   "docker-entrypoint.s…"   web        12 seconds ago   Up Less than a second     127.0.0.1:3000->3000/tcp
```

## Plan 03 handoff

Evidence Vault must use the versioned envelope, purpose-scoped blind index, explicit redaction and audited reveal boundaries for source locators, authority references and sensitive notes. It must not add auto-decrypting ORM properties or persist runtime keys.
