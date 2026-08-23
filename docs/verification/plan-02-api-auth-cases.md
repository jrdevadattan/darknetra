# Plan 02 — API, authentication, RBAC, and case lifecycle verification

- **Verified commit:** `638687ca6f5b8e2adb880a29c8c00c5df80cd6c0`
- **Observed at (UTC):** `2026-08-18T07:03:09Z`
- **Alembic head:** `670002e45670 (head)`
- **Runner:** GitHub Actions `ubuntu-latest`

## Command outcomes

| Gate | Observed outcome |
|---|---|
| Runtime-only JWT signing key | success |
| Documentation preflight | success |
| Locked workspace installation | success |
| Development + E2E Compose config | success |
| Disposable PostgreSQL | success |
| Alembic upgrade/downgrade/upgrade | success |
| `uv run ruff check .` | success |
| `uv run pytest -q` | success |
| Frontend Biome lint | success |
| Frontend TypeScript typecheck | success |
| Full frontend Vitest suite | success |
| Next.js production build | success |
| Chromium installation | success |
| Synthetic online/offline Playwright | success |
| Deterministic real-E2E fixture | success |
| Real API/web Compose stack | success |
| Real auth/cross-case Playwright | success |
| Disposable stack + volume teardown | success |
| `bash scripts/smoke.sh` | success |

## Observed summaries

### Migration round-trip

```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 670002e45670, create identity and case tables
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
670002e45670 (head)
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 670002e45670 -> , create identity and case tables
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 670002e45670, create identity and case tables
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
670002e45670 (head)
670002e45670 (head)
```

### Python suite

```text
..........................................................               [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/runner/work/darknetra/darknetra/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
58 passed, 1 warning in 6.07s
```

### Frontend suite

```text

> @darknetra/web@2.2.0 test /home/runner/work/darknetra/darknetra/apps/web
> vitest run

[33m(!) Your Vite config uses features that are unsupported by `configLoader: 'native'`, which is planned to become the default in a future major version of Vite:
  - ESM syntax in a file loaded as CommonJS (vitest.config.ts:1:1). Use a `.mjs` extension or set `"type": "module"` in the closest package.json
Set `VITE_CONFIG_NATIVE_IGNORE_WARNING=true` to suppress this warning.[39m

[1m[30m[46m RUN [49m[39m[22m [36mv4.1.10 [39m[90m/home/runner/work/darknetra/darknetra/apps/web[39m

 [32m✓[39m src/features/auth/auth-session.test.tsx [2m([22m[2m10 tests[22m[2m)[22m[33m 861[2mms[22m[39m
 [32m✓[39m src/features/cases/live-case-views.test.tsx [2m([22m[2m6 tests[22m[2m)[22m[32m 228[2mms[22m[39m
 [32m✓[39m src/features/admin/admin-reads.test.tsx [2m([22m[2m4 tests[22m[2m)[22m[32m 90[2mms[22m[39m
 [32m✓[39m src/lib/api/__tests__/client.test.ts [2m([22m[2m9 tests[22m[2m)[22m[32m 17[2mms[22m[39m
 [32m✓[39m src/features/overview/overview-live-view.test.tsx [2m([22m[2m2 tests[22m[2m)[22m[32m 206[2mms[22m[39m
 [32m✓[39m src/features/cases/queries.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 4[2mms[22m[39m
 [32m✓[39m src/lib/api/health.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/navigation/darknetra-navigation.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 4[2mms[22m[39m
 [32m✓[39m src/components/darknetra/investigator-primitives.test.tsx [2m([22m[2m9 tests[22m[2m)[22m[32m 140[2mms[22m[39m
 [32m✓[39m src/features/cases/cases-table.test.tsx [2m([22m[2m1 test[22m[2m)[22m[32m 275[2mms[22m[39m
 [32m✓[39m src/navigation/sidebar/sidebar-items.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 4[2mms[22m[39m
 [32m✓[39m src/config/metadata-contract.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 2[2mms[22m[39m
 [32m✓[39m src/config/app-config.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m

[2m Test Files [22m [1m[32m13 passed[39m[22m[90m (13)[39m
[2m      Tests [22m [1m[32m57 passed[39m[22m[90m (57)[39m
[2m   Start at [22m 06:58:28
[2m   Duration [22m 12.80s[2m (transform 382ms, setup 1.45s, import 1.61s, tests 1.84s, environment 6.51s)[22m

```

### Synthetic browser suite

```text

> @darknetra/web@2.2.0 test:e2e /home/runner/work/darknetra/darknetra/apps/web
> pnpm test:e2e:online && pnpm test:e2e:offline


> @darknetra/web@2.2.0 test:e2e:online /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright.config.ts

[WebServer] INFO:     Started server process [5593]
[WebServer] INFO:     Waiting for application startup.
[WebServer] INFO:     Application startup complete.
[WebServer] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 12 tests using 1 worker

  ✓   1 [desktop-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (618ms)
  ✓   2 [desktop-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (975ms)
  ✓   3 [desktop-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (942ms)
  ✓   4 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (691ms)
  ✓   5 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (819ms)
  ✓   6 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (635ms)
  ✓   7 [mobile-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (738ms)
  ✓   8 [mobile-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (813ms)
  ✓   9 [mobile-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (877ms)
  ✓  10 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (1.0s)
  ✓  11 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (755ms)
  ✓  12 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (553ms)

  12 passed (14.0s)

> @darknetra/web@2.2.0 test:e2e:offline /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright-offline.config.ts

[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 1 test using 1 worker

  ✓  1 [offline-chromium] › e2e/offline-health.spec.ts:3:5 › protected workspace reports authentication service outage without false content (629ms)

  1 passed (2.2s)
```

### Real authentication/authorization browser suite

```text

> @darknetra/web@2.2.0 test:e2e:real /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright-real.config.ts


Running 4 tests using 1 worker

  ✓  1 [real-auth-chromium] › e2e/auth.spec.ts:30:5 › bad password stays generic and clears the submitted secret (1.0s)
  ✓  2 [real-auth-chromium] › e2e/auth.spec.ts:38:5 › real login reaches the dashboard and logout revokes the browser session (2.1s)
  ✓  3 [real-auth-chromium] › e2e/auth.spec.ts:53:5 › bootstrap login is forced through password change before normal work (1.5s)
  ✓  4 [real-auth-chromium] › e2e/case-authorization.spec.ts:43:5 › inaccessible and unknown case IDs have the same 404 response and browser experience (1.7s)

  4 passed (7.0s)
```

### Docker smoke

```text

#35 [web] resolving provenance for metadata file
#35 DONE 0.0s
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
 Container darknetra-postgres-1  Healthy
 Container darknetra-api-1  Healthy
NAME                   IMAGE           COMMAND                  SERVICE    CREATED          STATUS                    PORTS
darknetra-api-1        darknetra-api   "uv run --no-sync uv…"   api        12 seconds ago   Up 6 seconds (healthy)    127.0.0.1:8000->8000/tcp
darknetra-postgres-1   postgres:18     "docker-entrypoint.s…"   postgres   12 seconds ago   Up 11 seconds (healthy)   127.0.0.1:5432->5432/tcp
darknetra-web-1        darknetra-web   "docker-entrypoint.s…"   web        12 seconds ago   Up Less than a second     127.0.0.1:3000->3000/tcp
```

## Architecture deviation

Plan 02 uses UUID4 until an approved UUIDv7 implementation is adopted; no custom UUID algorithm was introduced. See [ADR-0002](../decisions/0002-use-uuid4-until-approved-uuidv7.md).

## Plan 03 handoff

Plan 03 may rely on authenticated current-user context, authoritative PostgreSQL case identifiers, case-scoped authorization dependencies, rotating sessions with CSRF protection, the transactional append-only audit service, the async SQLAlchemy session factory, Alembic migrations, the typed frontend API client, and the protected case route shell.

Evidence ingestion and analytic features were not implemented or claimed by Plan 02.
