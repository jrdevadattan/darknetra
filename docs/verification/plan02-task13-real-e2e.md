# Plan 02 Task 13 verification

Real browser RED phase outcomes:

- prepare: success
- Compose profile: success
- disposable PostgreSQL: success
- migration: success
- real API/web stack: success
- Chromium install: success
- real auth/authorization browser tests: failure

## Browser test tail

```text

> @darknetra/web@2.2.0 test:e2e:real /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright-real.config.ts


Running 4 tests using 1 worker

  ✓  1 [real-auth-chromium] › e2e/auth.spec.ts:30:5 › bad password stays generic and clears the submitted secret (891ms)
  ✘  2 [real-auth-chromium] › e2e/auth.spec.ts:38:5 › real login reaches the dashboard and logout revokes the browser session (10.6s)
  -  3 [real-auth-chromium] › e2e/auth.spec.ts:53:5 › bootstrap login is forced through password change before normal work
  ✘  4 [real-auth-chromium] › e2e/case-authorization.spec.ts:43:5 › inaccessible and unknown case IDs have the same 404 response and browser experience (10.7s)


  1) [real-auth-chromium] › e2e/auth.spec.ts:38:5 › real login reaches the dashboard and logout revokes the browser session 

    Error: expect(page).toHaveURL(expected) failed

    Expected pattern: /\/dashboard$/
    Received string:  "http://127.0.0.1:3000/auth/v2/login"
    Timeout: 10000ms

    Call log:
      - Expect "toHaveURL" with timeout 10000ms
        24 × locator resolved to <html lang="en" data-font="geist" data-theme-mode="light" data-navbar-style="sticky" data-theme-preset="default" data-content-layout="centered" data-sidebar-variant="sidebar" data-sidebar-collapsible="icon">…</html>
           - unexpected value "http://127.0.0.1:3000/auth/v2/login"


      39 |   await signIn(page, ANALYST_USERNAME, ANALYST_PASSWORD);
      40 |
    > 41 |   await expect(page).toHaveURL(/\/dashboard$/);
         |                      ^
      42 |   await expect(page.getByRole('heading', { name: 'Investigator overview' })).toBeVisible();
      43 |   await expect(page.getByText('E2E Analyst A', { exact: true })).toBeVisible();
      44 |
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/auth.spec.ts:41:22

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/auth-real-login-reaches-th-67ee1-revokes-the-browser-session-real-auth-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/auth-real-login-reaches-th-67ee1-revokes-the-browser-session-real-auth-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/auth-real-login-reaches-th-67ee1-revokes-the-browser-session-real-auth-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/auth-real-login-reaches-th-67ee1-revokes-the-browser-session-real-auth-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  2) [real-auth-chromium] › e2e/case-authorization.spec.ts:43:5 › inaccessible and unknown case IDs have the same 404 response and browser experience 

    Error: expect(page).toHaveURL(expected) failed

    Expected pattern: /\/dashboard$/
    Received string:  "http://127.0.0.1:3000/auth/v2/login"
    Timeout: 10000ms

    Call log:
      - Expect "toHaveURL" with timeout 10000ms
        24 × locator resolved to <html lang="en" data-font="geist" data-theme-mode="light" data-navbar-style="sticky" data-theme-preset="default" data-content-layout="centered" data-sidebar-variant="sidebar" data-sidebar-collapsible="icon">…</html>
           - unexpected value "http://127.0.0.1:3000/auth/v2/login"


      20 |   await page.getByLabel('Password', { exact: true }).fill(ANALYST_A_PASSWORD);
      21 |   await page.getByRole('button', { name: 'Sign in' }).click();
    > 22 |   await expect(page).toHaveURL(/\/dashboard$/);
         |                      ^
      23 | }
      24 |
      25 | async function openCaseAndCaptureApi(
        at signIn (/home/runner/work/darknetra/darknetra/apps/web/e2e/case-authorization.spec.ts:22:22)
        at /home/runner/work/darknetra/darknetra/apps/web/e2e/case-authorization.spec.ts:46:3

    attachment #1: screenshot (image/png) ──────────────────────────────────────────────────────────
    test-results/case-authorization-inacces-ef4f7-onse-and-browser-experience-real-auth-chromium/test-failed-1.png
    ────────────────────────────────────────────────────────────────────────────────────────────────

    Error Context: test-results/case-authorization-inacces-ef4f7-onse-and-browser-experience-real-auth-chromium/error-context.md

    attachment #3: trace (application/zip) ─────────────────────────────────────────────────────────
    test-results/case-authorization-inacces-ef4f7-onse-and-browser-experience-real-auth-chromium/trace.zip
    Usage:

        pnpm exec playwright show-trace test-results/case-authorization-inacces-ef4f7-onse-and-browser-experience-real-auth-chromium/trace.zip

    ────────────────────────────────────────────────────────────────────────────────────────────────

  2 failed
    [real-auth-chromium] › e2e/auth.spec.ts:38:5 › real login reaches the dashboard and logout revokes the browser session 
    [real-auth-chromium] › e2e/case-authorization.spec.ts:43:5 › inaccessible and unknown case IDs have the same 404 response and browser experience 
  1 did not run
  1 passed (23.7s)
/home/runner/work/darknetra/darknetra/apps/web:
 ERR_PNPM_RECURSIVE_RUN_FIRST_FAIL  @darknetra/web@2.2.0 test:e2e:real: `playwright test --config playwright-real.config.ts`
Exit status 1
```
