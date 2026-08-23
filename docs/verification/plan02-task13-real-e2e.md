# Plan 02 Task 13 verification

Real authentication and authorization E2E outcomes:

- prepare: success
- fixture safety/style: success
- frontend lint/typecheck: success
- Compose profile: success
- disposable PostgreSQL: success
- migration: success
- deterministic fixture: success
- real API/web stack: success
- Chromium install: success
- real auth/authorization browser tests: success

## Fixture output

```json
{"cases": {"analyst_a": {"case_code": "E2E-A-001", "id": "00000000-0000-4000-8000-000000000ca1"}, "analyst_b": {"case_code": "E2E-B-001", "id": "00000000-0000-4000-8000-000000000cb1"}}, "users": {"analyst_a": {"id": "00000000-0000-4000-8000-0000000000a1", "username": "e2e.analyst.a"}, "analyst_b": {"id": "00000000-0000-4000-8000-0000000000b1", "username": "e2e.analyst.b"}, "bootstrap": {"id": "00000000-0000-4000-8000-0000000000c1", "username": "e2e.bootstrap"}}}
```

## Browser test tail

```text

> @darknetra/web@2.2.0 test:e2e:real /home/runner/work/darknetra/darknetra/apps/web
> playwright test --config playwright-real.config.ts


Running 4 tests using 1 worker

  ✓  1 [real-auth-chromium] › e2e/auth.spec.ts:30:5 › bad password stays generic and clears the submitted secret (1.1s)
  ✓  2 [real-auth-chromium] › e2e/auth.spec.ts:38:5 › real login reaches the dashboard and logout revokes the browser session (2.0s)
  ✓  3 [real-auth-chromium] › e2e/auth.spec.ts:53:5 › bootstrap login is forced through password change before normal work (2.1s)
  ✓  4 [real-auth-chromium] › e2e/case-authorization.spec.ts:43:5 › inaccessible and unknown case IDs have the same 404 response and browser experience (2.4s)

  4 passed (9.8s)
```
