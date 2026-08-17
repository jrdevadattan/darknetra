# DARKNETRA Foundation and Investigator Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the DARKNETRA monorepo, import the approved admin-dashboard snapshot reproducibly, remove unrelated showcase functionality, create the investigator navigation/route shell, add a real minimal FastAPI health boundary, and prove the web/API stack works through Docker Compose.

**Architecture:** `apps/web` is a Next.js investigator UI adapted from the pinned MIT-licensed upstream dashboard. `apps/api` is intentionally minimal in this plan: health/config only, so Docker and client/server connectivity are real without prematurely implementing cases/evidence. Root pnpm/uv tooling, tests, CI, attribution, and Compose are owned at repository root.

**Tech Stack:** Node.js 24 LTS, pnpm 10.x, Next.js 16.3.x, React 19.2.x, TypeScript 5.9.x, Tailwind CSS 4.x, retained shadcn/Radix primitives, Recharts, Vitest, Testing Library, Playwright, Python 3.12.x, FastAPI 0.135.x, Pydantic 2.x, pytest, Ruff, Docker Compose v2.

## Global Constraints

- Work only on `testing-codex`; `main` remains stable.
- Read the approved design, ADR-0001, and `docs/superpowers/plans/README.md` before editing.
- Upstream dashboard source is pinned to `arhamkhnz/next-shadcn-admin-dashboard@0c668859c4fdeaa0279c951c178b965cce62a125`.
- Preserve `LICENSES/next-shadcn-admin-dashboard-MIT.txt` and retained upstream copyright headers.
- Frontend bounds: Node 24; Next `>=16.2.11,<17`; React `19.2.x`; TypeScript `>=5.8,<6`; pnpm `10.x`; Tailwind `4.x`.
- Backend bounds: Python `3.12.x`; FastAPI `0.135.x`; Pydantic `2.x`.
- Use Recharts; do not add ECharts in this plan.
- No Tor, cloud LLM, GPU, Postgres, Redis, Neo4j, evidence processing, or criminal-source collection is required in Plan 01.
- The final dashboard must not retain ecommerce, CRM, finance, academy, generic mail/calendar/chat, or unrelated demo analytics surfaces.
- Every metric/card links to an actual work queue/route.
- Status is never color-only. Use `candidate`, `lead`, `pending analyst review`, `analyst-confirmed`, `rejected`; never automatic `criminal`/`guilty` labels.
- Fixtures contain fictional/synthetic values only; no operational onion locator, seller contact, real wallet, private key, evidence, secret, or unredacted personal data.
- No completion claim without fresh tests, lint, typecheck, production build, E2E, and Docker smoke output.

---

## Target repository shape

```text
apps/
  web/
  api/
packages/
  contracts/
  ui/README.md
  config/README.md
services/
  worker/README.md
  graph-projector/README.md
  collector/README.md
infrastructure/docker/
  web.Dockerfile
  api.Dockerfile
tests/repo/
scripts/
docs/vendor/
docs/verification/
docker-compose.yml
docker-compose.dev.yml
package.json
pnpm-workspace.yaml
pnpm-lock.yaml
pyproject.toml
uv.lock
.env.example
.node-version
.python-version
Makefile
```

---

### Task 1: Vendor provenance guardrail

**Files:**
- Create `docs/vendor/next-shadcn-admin-dashboard.md`
- Create `scripts/__init__.py`
- Create `scripts/check_repo_contract.py`
- Create `tests/repo/test_vendor_attribution.py`
- Verify `LICENSES/next-shadcn-admin-dashboard-MIT.txt`

**Interfaces:**
- `check_vendor_attribution(repo_root: Path) -> list[str]`.

- [ ] **Step 1: Verify branch**

```bash
test "$(git branch --show-current)" = "testing-codex"
git status --short
```

Stop if branch differs or unrelated changes exist.

- [ ] **Step 2: Write failing test**

```python
from pathlib import Path
from scripts.check_repo_contract import check_vendor_attribution


def test_dashboard_vendor_attribution() -> None:
    root = Path(__file__).resolve().parents[2]
    assert check_vendor_attribution(root) == []
```

Run:

```bash
python -m pytest tests/repo/test_vendor_attribution.py -v
```

Expected: import failure before implementation.

- [ ] **Step 3: Implement checker**

```python
from pathlib import Path

UPSTREAM_REPO = "arhamkhnz/next-shadcn-admin-dashboard"
UPSTREAM_COMMIT = "0c668859c4fdeaa0279c951c178b965cce62a125"


def check_vendor_attribution(repo_root: Path) -> list[str]:
    errors: list[str] = []
    license_path = repo_root / "LICENSES" / "next-shadcn-admin-dashboard-MIT.txt"
    vendor_doc = repo_root / "docs" / "vendor" / "next-shadcn-admin-dashboard.md"
    if not license_path.is_file():
        errors.append("missing upstream MIT license")
    else:
        text = license_path.read_text(encoding="utf-8")
        if "Copyright (c) 2024 Mohammed Arham Khan" not in text:
            errors.append("missing upstream copyright")
        if "MIT License" not in text:
            errors.append("missing MIT license text")
    if not vendor_doc.is_file():
        errors.append("missing vendor provenance")
    else:
        text = vendor_doc.read_text(encoding="utf-8")
        if UPSTREAM_REPO not in text:
            errors.append("missing upstream repo")
        if UPSTREAM_COMMIT not in text:
            errors.append("missing pinned commit")
    return errors
```

`docs/vendor/next-shadcn-admin-dashboard.md` must state upstream repo, exact SHA, MIT license, local license path, and that the snapshot is copied only as UI baseline and is not a runtime dependency.

- [ ] **Step 4: Verify and commit**

```bash
python -m pytest tests/repo/test_vendor_attribution.py -v
git add docs/vendor scripts tests/repo
git commit -m "test: guard dashboard vendor attribution"
```

---

### Task 2: Root pnpm/uv monorepo contract

**Files:**
- Create `package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `uv.lock`
- Create `.node-version`, `.python-version`, `.editorconfig`, `.gitignore`, `.env.example`, `Makefile`
- Create `tests/repo/test_workspace_contract.py`
- Create README-only boundaries in `packages/ui`, `packages/config`, `services/worker`, `services/graph-projector`, `services/collector`

**Interfaces:** root commands `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`; Make `bootstrap`, `dev`, `test`, `check`, `build`, `smoke`.

- [ ] **Step 1: Write failing workspace test**

```python
import json
from pathlib import Path


def test_root_workspace_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    workspace = (root / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert package["private"] is True
    assert package["packageManager"].startswith("pnpm@10.")
    assert package["engines"]["node"] == ">=24 <25"
    assert "apps/*" in workspace and "packages/*" in workspace
    assert (root / ".node-version").read_text().strip() == "24"
    assert (root / ".python-version").read_text().strip() == "3.12"
```

Run and confirm missing-file failure.

- [ ] **Step 2: Create exact root package files**

`package.json`:

```json
{
  "name": "darknetra",
  "version": "0.1.0",
  "private": true,
  "packageManager": "pnpm@10.15.0",
  "engines": { "node": ">=24 <25" },
  "scripts": {
    "dev": "pnpm --filter @darknetra/web dev",
    "lint": "pnpm -r --if-present lint",
    "typecheck": "pnpm -r --if-present typecheck",
    "test": "pnpm -r --if-present test",
    "build": "pnpm -r --if-present build",
    "check": "pnpm lint && pnpm typecheck && pnpm test && pnpm build"
  }
}
```

`pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

`pyproject.toml`:

```toml
[project]
name = "darknetra-dev"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
dev = ["pytest>=8.4,<9", "ruff>=0.12,<1"]

[tool.pytest.ini_options]
testpaths = ["tests", "apps/api/tests"]
pythonpath = [".", "apps/api"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

`.node-version` = `24`; `.python-version` = `3.12`.

`.env.example`:

```dotenv
DARKNETRA_ENVIRONMENT=development
DARKNETRA_BUILD_VERSION=dev
NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000
```

No secrets.

- [ ] **Step 3: Create repo defaults**

`.gitignore` must exclude `.env*` except `.env.example`, node_modules, pnpm store, `.next`, coverage, Playwright output, `.venv`, Python caches, IDE files, `data/`, `evidence-store/`.

`Makefile`:

```makefile
.PHONY: bootstrap dev test check build smoke

bootstrap:
	corepack enable
	pnpm install
	uv sync --dev

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

test:
	uv run pytest -q
	pnpm test

check:
	uv run ruff check .
	uv run pytest -q
	pnpm check

build:
	pnpm build
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build

smoke:
	bash scripts/smoke.sh
```

- [ ] **Step 4: Create future-service README boundaries**

They state responsibility only. `services/collector/README.md` explicitly says optional, policy-gated, read-only, disabled by default, and not required for finale.

- [ ] **Step 5: Lock and verify**

```bash
uv lock
uv sync --dev
uv run pytest tests/repo -v
```

- [ ] **Step 6: Commit**

```bash
git add package.json pnpm-workspace.yaml pyproject.toml uv.lock .node-version .python-version .editorconfig .gitignore .env.example Makefile packages services tests/repo
git commit -m "chore: establish DARKNETRA monorepo toolchain"
```

---

### Task 3: Import pinned dashboard snapshot cleanly

**Files:** `apps/web/**`, root `pnpm-lock.yaml`.

**Interfaces:** workspace package `@darknetra/web`.

- [ ] **Step 1: Clone exact source snapshot**

```bash
rm -rf /tmp/darknetra-dashboard-upstream
git clone --filter=blob:none https://github.com/arhamkhnz/next-shadcn-admin-dashboard.git /tmp/darknetra-dashboard-upstream
git -C /tmp/darknetra-dashboard-upstream checkout --detach 0c668859c4fdeaa0279c951c178b965cce62a125
test "$(git -C /tmp/darknetra-dashboard-upstream rev-parse HEAD)" = "0c668859c4fdeaa0279c951c178b965cce62a125"
```

- [ ] **Step 2: Copy source, remove nested repository automation/locks**

```bash
mkdir -p apps/web
rsync -a --delete --exclude='.git' --exclude='node_modules' --exclude='.next' /tmp/darknetra-dashboard-upstream/ apps/web/
rm -rf apps/web/.git apps/web/.github apps/web/.husky
rm -f apps/web/pnpm-lock.yaml apps/web/package-lock.json apps/web/yarn.lock apps/web/bun.lock apps/web/bun.lockb
```

Keep license text long enough to compare with repository attribution, then the repository `LICENSES/` copy remains required.

- [ ] **Step 3: Normalize `apps/web/package.json`**

Set `name`=`@darknetra/web`, `private`=true. Keep compatible framework/runtime versions from the pinned snapshot. Scripts must contain:

```json
{
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "biome lint",
  "format": "biome format --write",
  "check": "biome check",
  "check:fix": "biome check --write",
  "typecheck": "tsc --noEmit"
}
```

Remove nested Husky `prepare`, `lint-staged` config, and Husky/lint-staged devDependencies because repository hooks are not owned by a nested imported package.

Create `apps/web/UPSTREAM.md` with repo/SHA/license pointer.

- [ ] **Step 4: Install root workspace and verify upstream baseline before cleanup**

```bash
corepack enable
pnpm install
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web build
```

If the pinned snapshot itself fails under Node 24, capture exact failure and make the smallest compatibility correction; do not opportunistically upgrade the framework.

- [ ] **Step 5: Commit isolated upstream baseline**

```bash
git add apps/web pnpm-lock.yaml
git commit -m "chore: import pinned investigator dashboard baseline"
```

---

### Task 4: Add test harness, rebrand, and replace navigation before cleanup

**Files:** frontend Vitest/Playwright config, DARKNETRA navigation model/tests, root metadata.

**Interfaces:** `DARKNETRA_NAVIGATION`, `CASE_NAVIGATION`, `canSeeNavigationItem`.

- [ ] **Step 1: Install test dependencies in web workspace**

```bash
pnpm --filter @darknetra/web add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @playwright/test
pnpm --filter @darknetra/web exec playwright install chromium
```

Add scripts `test: vitest run`, `test:watch: vitest`, `test:e2e: playwright test`.

- [ ] **Step 2: Create Vitest setup/config** using jsdom and `@` alias to `apps/web/src`; add metadata test expecting title containing `DARKNETRA` and description containing `evidence`. Run and confirm it fails before metadata change.

- [ ] **Step 3: Change root metadata only** to:

```ts
export const metadata: Metadata = {
  title: "DARKNETRA — Investigator Intelligence",
  description: "Evidence-first narcotics intelligence for authorized investigators.",
}
```

- [ ] **Step 4: Write failing navigation test** asserting `/dashboard`, `/cases`, `/intelligence/trends`, `/admin/roles`, `/audit`, `/system/health`, and absence of `ecommerce|crm|finance|academy|mail|calendar|chat`.

- [ ] **Step 5: Implement navigation**

Global navigation:

```text
Overview -> /dashboard
Cases -> /cases
Intelligence -> /intelligence/trends, /intelligence/sources
Administration -> /admin/users, /admin/roles, /admin/taxonomies, /admin/settings
Audit -> /audit
System Health -> /system/health
```

Case tabs:

```text
Overview, Evidence, Entities, Activity Candidates, Link Analysis,
NarcoGraph, Timeline, Alerts, Reports
```

`NavigationItem` contains `title`, `href`, icon, optional `roles`, optional children. `canSeeNavigationItem` returns true with no required roles or when any required role is present.

- [ ] **Step 6: Wire retained shell/sidebar/mobile drawer to typed navigation** and test admin/auditor visibility and active route semantics.

- [ ] **Step 7: Run**

```bash
pnpm --filter @darknetra/web test
pnpm --filter @darknetra/web lint
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web build
```

- [ ] **Step 8: Commit** `test: establish DARKNETRA dashboard navigation contract`.

---

### Task 5: Delete unrelated template modules and prune proven-unused dependencies

**Files:** delete unrelated route/data/assets; modify package manifest/lock.

- [ ] **Step 1: Inventory imported top-level routes**

```bash
find 'apps/web/src/app/(main)/dashboard' -mindepth 1 -maxdepth 1 -type d -print | sort
```

- [ ] **Step 2: Delete only confirmed unrelated showcase route directories** corresponding to academy, analytics demo, calendar, chat demo, CRM, ecommerce, finance, generic mail, and other example dashboards not mapped by approved design. Retain shared `_components` only when still imported.

- [ ] **Step 3: Search stale references**

```bash
rg -n "ecommerce|crm|finance|academy|/mail|/calendar|/chat" apps/web/src || true
```

No navigation/import reference to deleted demo modules may remain.

- [ ] **Step 4: Prune dependencies only after import proof**. For each specialized candidate such as `@fullcalendar/react`, `d3-geo`, `topojson-client`, verify no source import using `rg` before `pnpm remove`. Keep shell/forms/table/theme/Recharts/auth presentation dependencies that remain used.

- [ ] **Step 5: Verify** test/lint/type/build and commit `refactor: remove unrelated admin dashboard demos`.

---

### Task 6: Build DARKNETRA investigator primitives and fixture-backed core route shell

**Files:**
- Create `apps/web/src/components/darknetra/{page-header,status-badge,metric-link-card,async-state,source-class-badge}.tsx` + tests.
- Create `apps/web/src/features/overview/**`, `features/cases/**`, `features/admin/roles/**`.
- Create all approved route shells.

**Interfaces:**
- Status values: `candidate`, `lead`, `pending-review`, `analyst-confirmed`, `rejected`, `verified`, `warning`, `failed`, `offline`.
- `CaseSummary`: id, title, status, sensitivity, sourceClass, owner, evidenceCount, pendingReviews, openAlerts, updatedAt.

- [ ] **Step 1: Write component tests** proving status text is visible, metric card is a link, AsyncState exposes loading/empty/error/partial/stale/offline, source class shows `SYNTHETIC`/`RESEARCH_ARCHIVE` text.

- [ ] **Step 2: Implement primitives using retained shadcn components**, preserving focus/contrast/theme behavior.

- [ ] **Step 3: Create safe fixture adapter** `getFixtureOverviewSnapshot()`; page components accept typed snapshot rather than importing raw fixture internals. Metrics: active cases, integrity warnings, pending link reviews, open alerts, failed jobs; each has href.

- [ ] **Step 4: Create Cases table** with fictional data, visible search/filter/sort/pagination and row link `/cases/{id}`.

- [ ] **Step 5: Create case-scoped route layout** and nine tab pages. In Plan 01 non-overview pages show precise scope state, e.g. Evidence route is ready but Evidence Vault API begins in Plan 03; do not fake analysis results.

- [ ] **Step 6: Create read-only role matrix** for exact roles `ADMIN, CASE_OWNER, COLLECTOR, ANALYST, REVIEWER, AUDITOR, VIEWER`; no fake Save action before Plan 02.

- [ ] **Step 7: Create route shells** for trends, sources, users, taxonomies, settings, audit, system health with explicit owner-plan copy rather than dead links.

- [ ] **Step 8: Verify** tests/lint/type/build and commit `feat: add investigator dashboard route shell`.

---

### Task 7: Add minimal real FastAPI health API and uv workspace

**Files:** `apps/api/**`, `packages/contracts/health.schema.json`, frontend health client/page.

**Interfaces:**
- `GET /api/v1/health/live` -> `{status:"ok",version:string}`
- `GET /api/v1/health/ready` -> `{status:"ready",version:string,components:[{name:"api",status:"ready"}]}`

- [ ] **Step 1: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "darknetra-api"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.135,<0.136",
  "pydantic-settings>=2.10,<3",
  "uvicorn[standard]>=0.35,<1",
]

[dependency-groups]
dev = ["pytest>=8.4,<9", "httpx>=0.28,<1"]
```

Add to root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = ["apps/api"]
```

Run `uv lock && uv sync --all-packages --dev`.

- [ ] **Step 2: Write failing FastAPI tests** for live/ready contracts.

- [ ] **Step 3: Implement** `Settings(environment="development",build_version="dev")` with prefix `DARKNETRA_`; implement health router and `FastAPI(title="DARKNETRA API", version="0.1.0")` under `/api/v1`.

- [ ] **Step 4: Create JSON Schema contract** for health responses and frontend `fetchHealth()` using `NEXT_PUBLIC_DARKNETRA_API_BASE_URL`, `AbortSignal.timeout(5000)`, typed non-2xx/network errors.

- [ ] **Step 5: System Health page** reports API reachable/unreachable honestly; no green state from page render alone.

- [ ] **Step 6: Verify** backend tests/Ruff + frontend tests/build and commit `feat: add minimal API health boundary`.

---

### Task 8: Dockerize web/API with exact non-root images and smoke script

**Files:** Dockerfiles, Compose, `.dockerignore`, `scripts/smoke.sh`, Compose contract test.

- [ ] **Step 1: Write failing repo test** asserting Compose exists and does not contain `privileged: true`, `network_mode: host`, or Docker socket mount.

- [ ] **Step 2: Create API Dockerfile**

```dockerfile
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --all-packages --no-dev
COPY apps/api apps/api
USER appuser
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "--app-dir", "apps/api", "darknetra_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Before final release, Plan 07 pins image digests. If uv version differs when implementation begins, use one explicit current 0.8.x version and record it; do not use `latest`.

- [ ] **Step 3: Configure Next standalone output** (`output: "standalone"`) and create web Dockerfile:

```dockerfile
FROM node:24-slim AS deps
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM deps AS builder
ARG NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_DARKNETRA_API_BASE_URL=$NEXT_PUBLIC_DARKNETRA_API_BASE_URL
COPY apps/web apps/web
RUN pnpm --filter @darknetra/web build

FROM node:24-slim AS runtime
ENV NODE_ENV=production
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/apps/web/.next/standalone ./
COPY --from=builder --chown=appuser:appuser /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=appuser:appuser /app/apps/web/public ./apps/web/public
USER appuser
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
```

If the standalone server output path differs in the pinned Next build, inspect `.next/standalone` and adjust COPY/CMD to observed output; do not weaken non-root behavior.

- [ ] **Step 4: Create Compose** base internal `app` bridge with `api` and `web`; dev overlay exposes `8000:8000`, `3000:3000`. API healthcheck calls localhost `/api/v1/health/live`; web depends on healthy API.

- [ ] **Step 5: Create smoke script**

```bash
#!/usr/bin/env bash
set -euo pipefail
compose=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)
cleanup() { "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${compose[@]}" up --build -d
"${compose[@]}" ps
python - <<'PY'
import json, urllib.request
body=json.load(urllib.request.urlopen('http://localhost:8000/api/v1/health/live', timeout=5))
assert body['status']=='ok'
urllib.request.urlopen('http://localhost:3000/dashboard', timeout=10).read(1024)
PY
```

- [ ] **Step 6: Run** Compose config, repo test, smoke; commit `chore: dockerize DARKNETRA web and API baseline`.

---

### Task 9: Add Playwright route regression, CI, and final verification

**Files:** E2E specs, `.github/workflows/ci.yml`, `.github/dependabot.yml`, development docs, verification record.

- [ ] **Step 1: E2E tests** verify desktop/mobile navigation, absence of removed showcase names, fixture case route and all nine case tabs, System Health reachable/unavailable behavior.

- [ ] **Step 2: CI jobs**

```text
python: uv sync --all-packages --dev; ruff; pytest
web: Node24/corepack; pnpm frozen install; lint; typecheck; test; build
docker: compose config; compose build
```

Dependabot weekly for npm, pip, Docker, GitHub Actions only.

- [ ] **Step 3: `docs/architecture/development.md`** includes exact native and Docker startup. Native API command:

```bash
uv run uvicorn --app-dir apps/api darknetra_api.main:app --reload
```

- [ ] **Step 4: Run final fresh verification**

```bash
uv run ruff check .
uv run pytest -q
pnpm --filter @darknetra/web lint
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web test
pnpm --filter @darknetra/web build
pnpm --filter @darknetra/web test:e2e
docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null
bash scripts/smoke.sh
rg -n "Ecommerce|CRM|Finance|Academy|Demo Chat|Mail Dashboard" apps/web/src || true
```

Inspect final `rg` output; expected no unrelated product/dashboard labels.

- [ ] **Step 5: Create `docs/verification/plan-01-foundation-dashboard.md`** with actual UTC time, commit SHA, commands, observed exit results, known limitations, and architecture deviations. Do not invent test counts.

- [ ] **Step 6: Commit** `docs: verify DARKNETRA foundation milestone`.

---

## Plan 01 Definition of Done

- Pinned upstream import is separately attributable and reproducible.
- Root pnpm/uv workspace is coherent; no nonexistent package is referenced by root scripts.
- Nested upstream lockfiles/Husky automation are removed; root lock owns dependencies.
- Unrelated showcase routes/data/dependencies are deleted, not hidden.
- DARKNETRA navigation and all approved route shells resolve.
- Overview metrics are actionable links; Cases/admin fixtures are synthetic and truthful about unimplemented backend scope.
- UI states remain accessible and uncertainty-aware.
- Minimal FastAPI health API is tested and connected to System Health UI.
- Web/API containers run non-root and Compose has no privileged/host/Docker-socket access.
- Native lint/type/test/build/E2E and Docker smoke pass with fresh evidence.
- Plan 02 can replace fixture-backed auth/cases without reworking the dashboard shell.