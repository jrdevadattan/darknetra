# Plan 02 Task 11 verification

GitHub Actions outcomes for authenticated session UX:

- prepare: success
- focused auth tests: success
- Biome lint: success
- TypeScript typecheck: success
- full frontend tests: success
- Next.js production build: success
- Chromium install: success
- online + offline Playwright suites: success

## Focused auth test tail

```text

> @darknetra/web@2.2.0 test /home/runner/work/darknetra/darknetra/apps/web
> vitest run -- src/features/auth

[33m(!) Your Vite config uses features that are unsupported by `configLoader: 'native'`, which is planned to become the default in a future major version of Vite:
  - ESM syntax in a file loaded as CommonJS (vitest.config.ts:1:1). Use a `.mjs` extension or set `"type": "module"` in the closest package.json
Set `VITE_CONFIG_NATIVE_IGNORE_WARNING=true` to suppress this warning.[39m

[1m[30m[46m RUN [49m[39m[22m [36mv4.1.10 [39m[90m/home/runner/work/darknetra/darknetra/apps/web[39m

 [32m✓[39m src/features/auth/auth-session.test.tsx [2m([22m[2m10 tests[22m[2m)[22m[33m 1038[2mms[22m[39m
     [33m[2m✓[22m[39m uses investigator credential semantics, supports keyboard submit, and clears the password [33m 371[2mms[22m[39m
 [32m✓[39m src/features/cases/live-case-views.test.tsx [2m([22m[2m6 tests[22m[2m)[22m[32m 298[2mms[22m[39m
 [32m✓[39m src/lib/api/__tests__/client.test.ts [2m([22m[2m9 tests[22m[2m)[22m[32m 22[2mms[22m[39m
 [32m✓[39m src/features/overview/overview-live-view.test.tsx [2m([22m[2m2 tests[22m[2m)[22m[32m 283[2mms[22m[39m
 [32m✓[39m src/features/cases/queries.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 6[2mms[22m[39m
 [32m✓[39m src/lib/api/health.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 7[2mms[22m[39m
 [32m✓[39m src/navigation/darknetra-navigation.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/components/darknetra/investigator-primitives.test.tsx [2m([22m[2m9 tests[22m[2m)[22m[32m 186[2mms[22m[39m
 [32m✓[39m src/features/cases/cases-table.test.tsx [2m([22m[2m1 test[22m[2m)[22m[33m 388[2mms[22m[39m
     [33m[2m✓[22m[39m supports visible search and links rows to a case [33m 387[2mms[22m[39m
 [32m✓[39m src/navigation/sidebar/sidebar-items.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/config/metadata-contract.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m
 [32m✓[39m src/config/app-config.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m

[2m Test Files [22m [1m[32m12 passed[39m[22m[90m (12)[39m
[2m      Tests [22m [1m[32m53 passed[39m[22m[90m (53)[39m
[2m   Start at [22m 23:28:24
[2m   Duration [22m 16.22s[2m (transform 421ms, setup 1.96s, import 1.89s, tests 2.25s, environment 8.35s)[22m

```

## Browser test tail

```text

> @darknetra/web@2.2.0 test:e2e /home/runner/work/darknetra/darknetra/apps/web
> pnpm test:e2e:online && pnpm test:e2e:offline


> @darknetra/web@2.2.0 test:e2e:online /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright.config.ts

[WebServer] INFO:     Started server process [3317]
[WebServer] INFO:     Waiting for application startup.
[WebServer] INFO:     Application startup complete.
[WebServer] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 12 tests using 1 worker

  ✓   1 [desktop-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (779ms)
  ✓   2 [desktop-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (1.2s)
  ✓   3 [desktop-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (1.1s)
  ✓   4 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (875ms)
  ✓   5 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (1.0s)
  ✓   6 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (814ms)
  ✓   7 [mobile-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (929ms)
  ✓   8 [mobile-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (1.1s)
  ✓   9 [mobile-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (1.1s)
  ✓  10 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (1.1s)
  ✓  11 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (940ms)
  ✓  12 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (803ms)

  12 passed (18.6s)

> @darknetra/web@2.2.0 test:e2e:offline /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright-offline.config.ts

[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 1 test using 1 worker

  ✓  1 [offline-chromium] › e2e/offline-health.spec.ts:3:5 › protected workspace reports authentication service outage without false content (868ms)

  1 passed (2.6s)
```
