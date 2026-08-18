# Plan 02 — API, authentication, RBAC, and case lifecycle verification

- **Verified commit:** `088b9efeb2f17d4bfffb3af1e5b5e5c7dd9da448`
- **Observed at (UTC):** `2026-08-18T06:39:30Z`
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
| `uv run pytest -q` | failure |
| Frontend Biome lint | success |
| Frontend TypeScript typecheck | success |
| Full frontend Vitest suite | success |
| Next.js production build | success |
| Chromium installation | success |
| Synthetic online/offline Playwright | success |
| Deterministic real-E2E fixture | skipped |
| Real API/web Compose stack | skipped |
| Real auth/cross-case Playwright | skipped |
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
  
  Omitting 1 identical items, use -vv to show
  Differing items:
  {'version': 'plan02-final-verification'} != {'version': 'dev'}
  
  Full diff:
    {
        'status': 'ok',
  -     'version': 'dev',
  +     'version': 'plan02-final-verification',
    }
FAILED apps/api/tests/test_health.py::test_ready_health_contract - AssertionError: assert {'components'...verification'} == {'components'...rsion': 'dev'}
  
  Omitting 2 identical items, use -vv to show
  Differing items:
  {'version': 'plan02-final-verification'} != {'version': 'dev'}
  
  Full diff:
    {
        'components': [
            {
                'name': 'api',
                'status': 'ready',
            },
        ],
        'status': 'ready',
  -     'version': 'dev',
  +     'version': 'plan02-final-verification',
    }
2 failed, 56 passed, 1 warning in 6.54s
```

### Frontend suite

```text

> @darknetra/web@2.2.0 test /home/runner/work/darknetra/darknetra/apps/web
> vitest run

[33m(!) Your Vite config uses features that are unsupported by `configLoader: 'native'`, which is planned to become the default in a future major version of Vite:
  - ESM syntax in a file loaded as CommonJS (vitest.config.ts:1:1). Use a `.mjs` extension or set `"type": "module"` in the closest package.json
Set `VITE_CONFIG_NATIVE_IGNORE_WARNING=true` to suppress this warning.[39m

[1m[30m[46m RUN [49m[39m[22m [36mv4.1.10 [39m[90m/home/runner/work/darknetra/darknetra/apps/web[39m

 [32m✓[39m src/features/auth/auth-session.test.tsx [2m([22m[2m10 tests[22m[2m)[22m[33m 1033[2mms[22m[39m
     [33m[2m✓[22m[39m uses investigator credential semantics, supports keyboard submit, and clears the password [33m 368[2mms[22m[39m
 [32m✓[39m src/features/cases/live-case-views.test.tsx [2m([22m[2m6 tests[22m[2m)[22m[33m 307[2mms[22m[39m
 [32m✓[39m src/features/admin/admin-reads.test.tsx [2m([22m[2m4 tests[22m[2m)[22m[32m 119[2mms[22m[39m
 [32m✓[39m src/lib/api/__tests__/client.test.ts [2m([22m[2m9 tests[22m[2m)[22m[32m 22[2mms[22m[39m
 [32m✓[39m src/features/overview/overview-live-view.test.tsx [2m([22m[2m2 tests[22m[2m)[22m[32m 292[2mms[22m[39m
 [32m✓[39m src/features/cases/queries.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 8[2mms[22m[39m
 [32m✓[39m src/lib/api/health.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 7[2mms[22m[39m
 [32m✓[39m src/navigation/darknetra-navigation.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/components/darknetra/investigator-primitives.test.tsx [2m([22m[2m9 tests[22m[2m)[22m[32m 186[2mms[22m[39m
 [32m✓[39m src/features/cases/cases-table.test.tsx [2m([22m[2m1 test[22m[2m)[22m[33m 411[2mms[22m[39m
     [33m[2m✓[22m[39m supports visible search and links rows to a case [33m 410[2mms[22m[39m
 [32m✓[39m src/navigation/sidebar/sidebar-items.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/config/metadata-contract.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m
 [32m✓[39m src/config/app-config.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 4[2mms[22m[39m

[2m Test Files [22m [1m[32m13 passed[39m[22m[90m (13)[39m
[2m      Tests [22m [1m[32m57 passed[39m[22m[90m (57)[39m
[2m   Start at [22m 06:35:58
[2m   Duration [22m 17.90s[2m (transform 403ms, setup 2.23s, import 2.13s, tests 2.40s, environment 9.15s)[22m

```

### Synthetic browser suite

```text

> @darknetra/web@2.2.0 test:e2e /home/runner/work/darknetra/darknetra/apps/web
> pnpm test:e2e:online && pnpm test:e2e:offline


> @darknetra/web@2.2.0 test:e2e:online /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright.config.ts

[WebServer] INFO:     Started server process [5766]
[WebServer] INFO:     Waiting for application startup.
[WebServer] INFO:     Application startup complete.
[WebServer] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 12 tests using 1 worker

  ✓   1 [desktop-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (922ms)
  ✓   2 [desktop-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (1.1s)
  ✓   3 [desktop-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (1.2s)
  ✓   4 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (854ms)
  ✓   5 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (999ms)
  ✓   6 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (882ms)
  ✓   7 [mobile-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (892ms)
  ✓   8 [mobile-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (1.1s)
  ✓   9 [mobile-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (1.1s)
  ✓  10 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (1.3s)
  ✓  11 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (954ms)
  ✓  12 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (745ms)

  12 passed (17.6s)

> @darknetra/web@2.2.0 test:e2e:offline /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright-offline.config.ts

[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 1 test using 1 worker

  ✓  1 [offline-chromium] › e2e/offline-health.spec.ts:3:5 › protected workspace reports authentication service outage without false content (799ms)

  1 passed (2.6s)
```

### Real authentication/authorization browser suite

```text
```

### Docker smoke

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
 Container darknetra-postgres-1  Healthy
 Container darknetra-api-1  Healthy
NAME                   IMAGE           COMMAND                  SERVICE    CREATED          STATUS                    PORTS
darknetra-api-1        darknetra-api   "uv run --no-sync uv…"   api        12 seconds ago   Up 6 seconds (healthy)    127.0.0.1:8000->8000/tcp
darknetra-postgres-1   postgres:18     "docker-entrypoint.s…"   postgres   12 seconds ago   Up 12 seconds (healthy)   127.0.0.1:5432->5432/tcp
darknetra-web-1        darknetra-web   "docker-entrypoint.s…"   web        12 seconds ago   Up Less than a second     127.0.0.1:3000->3000/tcp
```

## Architecture deviation

Plan 02 uses UUID4 until an approved UUIDv7 implementation is adopted; no custom UUID algorithm was introduced. See [ADR-0002](../decisions/0002-use-uuid4-until-approved-uuidv7.md).

## Plan 03 handoff

Plan 03 may rely on authenticated current-user context, authoritative PostgreSQL case identifiers, case-scoped authorization dependencies, rotating sessions with CSRF protection, the transactional append-only audit service, the async SQLAlchemy session factory, Alembic migrations, the typed frontend API client, and the protected case route shell.

Evidence ingestion and analytic features were not implemented or claimed by Plan 02.
