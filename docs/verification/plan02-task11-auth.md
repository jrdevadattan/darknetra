# Plan 02 Task 11 verification

GitHub Actions outcomes for authenticated session UX:

- prepare: success
- focused auth tests: success
- Biome lint: success
- TypeScript typecheck: success
- full frontend tests: success
- Next.js production build: success
- Chromium install: success
- online + offline Playwright suites: failure

## Focused auth test tail

```text

> @darknetra/web@2.2.0 test /home/runner/work/darknetra/darknetra/apps/web
> vitest run -- src/features/auth

[33m(!) Your Vite config uses features that are unsupported by `configLoader: 'native'`, which is planned to become the default in a future major version of Vite:
  - ESM syntax in a file loaded as CommonJS (vitest.config.ts:1:1). Use a `.mjs` extension or set `"type": "module"` in the closest package.json
Set `VITE_CONFIG_NATIVE_IGNORE_WARNING=true` to suppress this warning.[39m

[1m[30m[46m RUN [49m[39m[22m [36mv4.1.10 [39m[90m/home/runner/work/darknetra/darknetra/apps/web[39m

 [32m✓[39m src/features/auth/auth-session.test.tsx [2m([22m[2m10 tests[22m[2m)[22m[33m 973[2mms[22m[39m
     [33m[2m✓[22m[39m uses investigator credential semantics, supports keyboard submit, and clears the password [33m 353[2mms[22m[39m
 [32m✓[39m src/features/cases/live-case-views.test.tsx [2m([22m[2m6 tests[22m[2m)[22m[32m 281[2mms[22m[39m
 [32m✓[39m src/lib/api/__tests__/client.test.ts [2m([22m[2m9 tests[22m[2m)[22m[32m 20[2mms[22m[39m
 [32m✓[39m src/features/overview/overview-live-view.test.tsx [2m([22m[2m2 tests[22m[2m)[22m[32m 265[2mms[22m[39m
 [32m✓[39m src/features/cases/queries.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/lib/api/health.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 6[2mms[22m[39m
 [32m✓[39m src/navigation/darknetra-navigation.test.ts [2m([22m[2m3 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/components/darknetra/investigator-primitives.test.tsx [2m([22m[2m9 tests[22m[2m)[22m[32m 170[2mms[22m[39m
 [32m✓[39m src/features/cases/cases-table.test.tsx [2m([22m[2m1 test[22m[2m)[22m[33m 321[2mms[22m[39m
     [33m[2m✓[22m[39m supports visible search and links rows to a case [33m 319[2mms[22m[39m
 [32m✓[39m src/navigation/sidebar/sidebar-items.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 5[2mms[22m[39m
 [32m✓[39m src/config/metadata-contract.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m
 [32m✓[39m src/config/app-config.test.ts [2m([22m[2m1 test[22m[2m)[22m[32m 3[2mms[22m[39m

[2m Test Files [22m [1m[32m12 passed[39m[22m[90m (12)[39m
[2m      Tests [22m [1m[32m53 passed[39m[22m[90m (53)[39m
[2m   Start at [22m 23:24:07
[2m   Duration [22m 15.55s[2m (transform 388ms, setup 1.86s, import 1.81s, tests 2.06s, environment 8.15s)[22m

```

## Browser test tail

```text

> @darknetra/web@2.2.0 test:e2e:online /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright.config.ts

[WebServer] INFO:     Started server process [3423]
[WebServer] INFO:     Waiting for application startup.
[WebServer] INFO:     Application startup complete.
[WebServer] INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
[WebServer] ⚠ "next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.

Running 12 tests using 1 worker

  ✓   1 [desktop-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (904ms)
  ✓   2 [desktop-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (1.4s)
  ✘   3 [desktop-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (1.0s)
  ✓   4 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (1.2s)
  ✓   5 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (1.3s)
  ✓   6 [desktop-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (1.1s)
  ✓   7 [mobile-chromium] › e2e/online/auth-session.spec.ts:22:5 › bad password stays generic and clears the password field (990ms)
  ✘   8 [mobile-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX (9.2s)
  ✘   9 [mobile-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds (1.2s)
  ✓  10 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:33:5 › desktop and mobile navigation expose only DARKNETRA workspaces (1.5s)
  ✓  11 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:48:5 › live case exposes all nine investigation tabs (1.1s)
  ✓  12 [mobile-chromium] › e2e/online/investigator-workspace.spec.ts:64:5 › System Health reports a measured reachable API for an authenticated session (783ms)


  1) [desktop-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds 

    Error: locator.fill: Error: strict mode violation: getByLabel('New password') resolved to 2 elements:
        1) <input value="" required="" minlength="12" maxlength="128" type="password" data-slot="input" name="new-password" id="darknetra-new-password" autocomplete="new-password" class="h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-…/> aka getByRole('textbox', { name: 'New password', exact: true })
        2) <input value="" required="" minlength="12" maxlength="128" type="password" data-slot="input" name="confirm-password" autocomplete="new-password" id="darknetra-confirm-password" class="h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visib…/> aka getByRole('textbox', { name: 'Confirm new password' })

    Call log:
      - waiting for getByLabel('New password')


       96 |   await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
       97 |
    >  98 |   await page.getByLabel('New password').fill('Replacement-Password-42!');
          |                                         ^
       99 |   await page.getByLabel('Confirm new password').fill('Replacement-Password-42!');
      100 |   await page.getByRole('button', { name: 'Update password' }).click();
      101 |
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/auth-session.spec.ts:98:41

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-desktop-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-desktop-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-desktop-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-desktop-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  2) [mobile-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX 

    Error: expect(locator).toBeVisible() failed

    Locator:  getByText('Investigator One')
    Expected: visible
    Received: hidden
    Timeout:  8000ms

    Call log:
      - Expect "toBeVisible" with timeout 8000ms
      - waiting for getByText('Investigator One')
        20 × locator resolved to <p class="max-w-44 truncate font-medium text-xs">Investigator One</p>
           - unexpected value "hidden"


      57 |   await expect(page).toHaveURL(/\/dashboard$/);
      58 |   await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();
    > 59 |   await expect(page.getByText('Investigator One')).toBeVisible();
         |                                                    ^
      60 |
      61 |   await page.getByRole('button', { name: 'Sign out' }).click();
      62 |   await expect(page).toHaveURL(/\/auth\/v2\/login$/);
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/auth-session.spec.ts:59:52

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/auth-session-normal-login--c36fb-ogout-clears-the-session-UX-mobile-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/auth-session-normal-login--c36fb-ogout-clears-the-session-UX-mobile-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/auth-session-normal-login--c36fb-ogout-clears-the-session-UX-mobile-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/auth-session-normal-login--c36fb-ogout-clears-the-session-UX-mobile-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  3) [mobile-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds 

    Error: locator.fill: Error: strict mode violation: getByLabel('New password') resolved to 2 elements:
        1) <input value="" required="" minlength="12" maxlength="128" type="password" data-slot="input" name="new-password" id="darknetra-new-password" autocomplete="new-password" class="h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-…/> aka getByRole('textbox', { name: 'New password', exact: true })
        2) <input value="" required="" minlength="12" maxlength="128" type="password" data-slot="input" name="confirm-password" autocomplete="new-password" id="darknetra-confirm-password" class="h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visib…/> aka getByRole('textbox', { name: 'Confirm new password' })

    Call log:
      - waiting for getByLabel('New password')


       96 |   await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
       97 |
    >  98 |   await page.getByLabel('New password').fill('Replacement-Password-42!');
          |                                         ^
       99 |   await page.getByLabel('Confirm new password').fill('Replacement-Password-42!');
      100 |   await page.getByRole('button', { name: 'Update password' }).click();
      101 |
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/online/auth-session.spec.ts:98:41

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-mobile-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-mobile-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-mobile-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/auth-session-forced-change-b9cba-il-password-update-succeeds-mobile-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  3 failed
    [desktop-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds 
    [mobile-chromium] › e2e/online/auth-session.spec.ts:37:5 › normal login enters the dashboard and logout clears the session UX 
    [mobile-chromium] › e2e/online/auth-session.spec.ts:66:5 › forced-change login cannot enter the dashboard until password update succeeds 
  9 passed (29.9s)
 ELIFECYCLE  Command failed with exit code 1.
/home/runner/work/darknetra/darknetra/apps/web:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @darknetra/web@2.2.0 test:e2e: `pnpm test:e2e:online && pnpm test:e2e:offline`
Exit status 1
```
