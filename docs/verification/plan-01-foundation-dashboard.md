# Plan 01 — Foundation and Investigator Dashboard Verification

- Verified at (UTC): `2026-08-17T18:53:16Z`
- Verified code commit: `defe52701f9c087ed60aea783f16a34a57bbb59a`
- Branch: `testing-codex`

## Fresh verification results

The exact code commit above completed successfully with:

- `uv run ruff check .`
- `uv run pytest -q`
- `pnpm --filter @darknetra/web lint`
- `pnpm --filter @darknetra/web typecheck`
- `pnpm --filter @darknetra/web test`
- `pnpm --filter @darknetra/web build`
- `pnpm --filter @darknetra/web test:e2e` in reachable-API and unavailable-API modes
- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config`
- `bash scripts/smoke.sh`
- the final unrelated-showcase label scan, with no matches

## Architecture deviations and observations

- The web runtime image includes the built pnpm workspace `node_modules` plus Next standalone output because the pinned Next/pnpm build retained pnpm-store runtime references; reliability is prioritized over minimum image size for this milestone.
- uv is pinned to `0.12.4` in Docker and verification tooling.
- The imported template has no `apps/web/public` directory, so the runtime image does not copy a nonexistent asset directory.
- The unreachable FullCalendar component was deleted before dependency removal, and `@fullcalendar/react` is no longer retained.

## Known limitations

Persistent authentication, users, case-scoped RBAC, PostgreSQL, and audit persistence begin in Plan 02. Current case and overview data are controlled fixtures. Evidence, extraction, correlation, graph, trends, and reports remain truthful interface boundaries rather than fabricated production results. The optional lawful collector remains disabled and unnecessary for startup or verification.
