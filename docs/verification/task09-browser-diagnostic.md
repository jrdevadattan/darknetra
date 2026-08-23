# Task 09 browser diagnostic

- build_status: 0
- e2e_status: 1

## Build log tail
```text

> @darknetra/web@2.2.0 build /home/runner/work/darknetra/darknetra/apps/web
> next build

▲ Next.js 16.3.1 (Turbopack)
✓ Running next.config.mjs took 16ms
⚠ No build cache found. Please configure build caching for faster rebuilds. Read more: https://nextjs.org/docs/messages/no-cache
Attention: Next.js now collects completely anonymous telemetry regarding usage.
This information is used to shape Next.js' roadmap and prioritize features.
You can learn more, including how to opt-out if you'd not like to participate in this anonymous program, by visiting the following URL:
https://nextjs.org/telemetry


  Creating an optimized production build ...
✓ Compiled successfully in 19.3s
  Running TypeScript ...
  Finished TypeScript in 8.6s ...
  Collecting page data using 1 worker ...
  Generating static pages using 1 worker (0/18) ...
  Generating static pages using 1 worker (4/18) 
  Generating static pages using 1 worker (8/18) 
  Generating static pages using 1 worker (13/18) 
✓ Generating static pages using 1 worker (18/18) in 482ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /admin/roles
├ ƒ /admin/settings
├ ƒ /admin/taxonomies
├ ƒ /admin/users
├ ƒ /audit
├ ○ /auth/v1/login
├ ○ /auth/v1/register
├ ○ /auth/v2/login
├ ○ /auth/v2/register
├ ƒ /cases
├ ƒ /cases/[caseId]
├ ƒ /cases/[caseId]/activity
├ ƒ /cases/[caseId]/alerts
├ ƒ /cases/[caseId]/entities
├ ƒ /cases/[caseId]/evidence
├ ƒ /cases/[caseId]/graph
├ ƒ /cases/[caseId]/links
├ ƒ /cases/[caseId]/reports
├ ƒ /cases/[caseId]/timeline
├ ƒ /dashboard
├ ƒ /dashboard/[...not-found]
├ ƒ /intelligence/sources
├ ƒ /intelligence/trends
├ ƒ /system/health
└ ○ /unauthorized


○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand

```

## E2E log tail
```text

> @darknetra/web@2.2.0 test:e2e /home/runner/work/darknetra/darknetra/apps/web
> pnpm test:e2e:online && pnpm test:e2e:offline


> @darknetra/web@2.2.0 test:e2e:online /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright.config.ts

[WebServer] INFO:     Started server process [3004]
[WebServer] INFO:     Waiting for application startup.
[WebServer] INFO:     Application startup complete.
[WebServer] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 6 tests using 1 worker

  ✓  1 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:8:5 › desktop and mobile navigation expose DARKNETRA workspaces (757ms)
  ✘  2 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:17:5 › fixture case exposes all nine investigation tabs (8.9s)
  ✘  3 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:29:5 › System Health reports a measured reachable API (9.0s)
  ✓  4 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:8:5 › desktop and mobile navigation expose DARKNETRA workspaces (1.3s)
  ✘  5 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:17:5 › fixture case exposes all nine investigation tabs (9.0s)
  ✘  6 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:29:5 › System Health reports a measured reachable API (8.9s)


  1) [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:17:5 › fixture case exposes all nine investigation tabs 

    Error: expect(locator).toBeVisible() failed

    Locator: getByText('Evidence Vault begins in Plan 03')
    Expected: visible
    Timeout: 8000ms
    Error: element(s) not found

    Call log:
      - Expect "toBeVisible" with timeout 8000ms
      - waiting for getByText('Evidence Vault begins in Plan 03')


      24 |   await caseNav.getByRole('link', { name: 'Evidence', exact: true }).click();
      25 |   await expect(page).toHaveURL(/\/cases\/SYN-DEMO-001\/evidence$/);
    > 26 |   await expect(page.getByText('Evidence Vault begins in Plan 03')).toBeVisible();
         |                                                                    ^
      27 | });
      28 |
      29 | test('System Health reports a measured reachable API', async ({ page }) => {
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/investigator-workspace.spec.ts:26:68

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-desktop-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-desktop-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-desktop-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-desktop-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  2) [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:29:5 › System Health reports a measured reachable API 

    Error: expect(locator).toBeVisible() failed

    Locator: getByText('ready', { exact: true })
    Expected: visible
    Timeout: 8000ms
    Error: element(s) not found

    Call log:
      - Expect "toBeVisible" with timeout 8000ms
      - waiting for getByText('ready', { exact: true })


      32 |   await expect(page.getByText('DARKNETRA API', { exact: true })).toBeVisible();
      33 |   await expect(page.getByText('Verified', { exact: true })).toBeVisible();
    > 34 |   await expect(page.getByText('ready', { exact: true })).toBeVisible();
         |                                                          ^
      35 | });
      36 |
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/investigator-workspace.spec.ts:34:58

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-desktop-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-desktop-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-desktop-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-desktop-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  3) [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:17:5 › fixture case exposes all nine investigation tabs 

    Error: expect(locator).toBeVisible() failed

    Locator: getByText('Evidence Vault begins in Plan 03')
    Expected: visible
    Timeout: 8000ms
    Error: element(s) not found

    Call log:
      - Expect "toBeVisible" with timeout 8000ms
      - waiting for getByText('Evidence Vault begins in Plan 03')


      24 |   await caseNav.getByRole('link', { name: 'Evidence', exact: true }).click();
      25 |   await expect(page).toHaveURL(/\/cases\/SYN-DEMO-001\/evidence$/);
    > 26 |   await expect(page.getByText('Evidence Vault begins in Plan 03')).toBeVisible();
         |                                                                    ^
      27 | });
      28 |
      29 | test('System Health reports a measured reachable API', async ({ page }) => {
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/investigator-workspace.spec.ts:26:68

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-mobile-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-mobile-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-mobile-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/investigator-workspace-fix-2c746-all-nine-investigation-tabs-mobile-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  4) [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:29:5 › System Health reports a measured reachable API 

    Error: expect(locator).toBeVisible() failed

    Locator: getByText('ready', { exact: true })
    Expected: visible
    Timeout: 8000ms
    Error: element(s) not found

    Call log:
      - Expect "toBeVisible" with timeout 8000ms
      - waiting for getByText('ready', { exact: true })


      32 |   await expect(page.getByText('DARKNETRA API', { exact: true })).toBeVisible();
      33 |   await expect(page.getByText('Verified', { exact: true })).toBeVisible();
    > 34 |   await expect(page.getByText('ready', { exact: true })).toBeVisible();
         |                                                          ^
      35 | });
      36 |
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/investigator-workspace.spec.ts:34:58

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-mobile-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-mobile-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-mobile-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/investigator-workspace-Sys-d2cc0-ts-a-measured-reachable-API-mobile-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  4 failed
    [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:17:5 › fixture case exposes all nine investigation tabs 
    [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:29:5 › System Health reports a measured reachable API 
    [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:17:5 › fixture case exposes all nine investigation tabs 
    [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:29:5 › System Health reports a measured reachable API 
  2 passed (44.3s)
 ELIFECYCLE  Command failed with exit code 1.
/home/runner/work/darknetra/darknetra/apps/web:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @darknetra/web@2.2.0 test:e2e: `pnpm test:e2e:online && pnpm test:e2e:offline`
Exit status 1
```
