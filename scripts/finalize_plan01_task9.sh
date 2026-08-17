#!/usr/bin/env bash
set -euo pipefail

run_gate() {
  test -f .github/workflows/ci.yml
  test -f .github/dependabot.yml
  test -f docs/architecture/development.md
  test -f apps/web/playwright.config.ts
  test -f apps/web/playwright-offline.config.ts

  uv run ruff check .
  uv run pytest -q
  pnpm --filter @darknetra/web lint
  pnpm --filter @darknetra/web typecheck
  pnpm --filter @darknetra/web test
  pnpm --filter @darknetra/web build
  pnpm --filter @darknetra/web test:e2e
  docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null
  bash scripts/smoke.sh
  ! grep -R -n -E 'Ecommerce|CRM|Finance|Academy|Demo Chat|Mail Dashboard' apps/web/src
}

if git grep -n -F '@fullcalendar/react' -- apps/web/src; then
  echo 'Tracked product source still imports @fullcalendar/react.' >&2
  exit 1
fi

python - <<'PY'
from pathlib import Path

path = Path('tests/repo/test_frontend_surface.py')
text = path.read_text(encoding='utf-8')
if not text.startswith('import json\n'):
    text = 'import json\n' + text
addition = '''\n\ndef test_calendar_showcase_dependency_is_not_retained() -> None:\n    package = json.loads((WEB / "package.json").read_text(encoding="utf-8"))\n    assert "@fullcalendar/react" not in package.get("dependencies", {})\n'''
if 'test_calendar_showcase_dependency_is_not_retained' not in text:
    text += addition
path.write_text(text, encoding='utf-8')
PY

set +e
uv run pytest tests/repo/test_frontend_surface.py::test_calendar_showcase_dependency_is_not_retained -v >/tmp/calendar-red.log 2>&1
red_status=$?
set -e
cat /tmp/calendar-red.log
if [ "$red_status" -eq 0 ]; then
  echo 'Expected calendar dependency guard to fail before package removal.' >&2
  exit 1
fi

pnpm --filter @darknetra/web remove @fullcalendar/react
uv run pytest tests/repo/test_frontend_surface.py::test_calendar_showcase_dependency_is_not_retained -v

run_gate

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add apps/web/package.json pnpm-lock.yaml tests/repo/test_frontend_surface.py
git commit -m 'test: complete Plan 01 browser regression gate [skip ci]'
git push origin HEAD:testing-codex
verified_candidate_sha="$(git rev-parse HEAD)"

test -z "$(git status --porcelain)"
run_gate

test "$(git rev-parse HEAD)" = "$verified_candidate_sha"
verified_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
mkdir -p docs/verification
cat > docs/verification/plan-01-foundation-dashboard.md <<EOF
# Plan 01 — Foundation and Investigator Dashboard Verification

- Verified at (UTC): \`${verified_at}\`
- Verified code commit: \`${verified_candidate_sha}\`
- Branch: \`testing-codex\`

## Fresh verification results

The exact code commit above completed successfully with:

- \`uv run ruff check .\`
- \`uv run pytest -q\`
- \`pnpm --filter @darknetra/web lint\`
- \`pnpm --filter @darknetra/web typecheck\`
- \`pnpm --filter @darknetra/web test\`
- \`pnpm --filter @darknetra/web build\`
- \`pnpm --filter @darknetra/web test:e2e\` in reachable-API and unavailable-API modes
- \`docker compose -f docker-compose.yml -f docker-compose.dev.yml config\`
- \`bash scripts/smoke.sh\`
- the final unrelated-showcase label scan, with no matches

## Architecture deviations and observations

- The web runtime image includes the built pnpm workspace \`node_modules\` plus Next standalone output because the pinned Next/pnpm build retained pnpm-store runtime references; reliability is prioritized over minimum image size for this milestone.
- uv is pinned to \`0.12.4\` in Docker and verification tooling.
- The imported template has no \`apps/web/public\` directory, so the runtime image does not copy a nonexistent asset directory.
- The unreachable FullCalendar component was deleted before dependency removal, and \`@fullcalendar/react\` is no longer retained.

## Known limitations

Persistent authentication, users, case-scoped RBAC, PostgreSQL, and audit persistence begin in Plan 02. Current case and overview data are controlled fixtures. Evidence, extraction, correlation, graph, trends, and reports remain truthful interface boundaries rather than fabricated production results. The optional lawful collector remains disabled and unnecessary for startup or verification.
EOF

git add docs/verification/plan-01-foundation-dashboard.md
git commit -m 'docs: verify DARKNETRA foundation milestone [skip ci]'
git push origin HEAD:testing-codex
