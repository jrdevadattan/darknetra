# DARKNETRA

> **Evidence-first, multilingual narcotics-intelligence and criminal-network discovery platform for authorized investigators.**

DARKNETRA is being developed for the **Chandigarh Police National Hackathon 2026 — Problem Statement 3**. The product direction is to preserve source evidence, extract structured narcotics indicators, correlate cross-platform aliases, visualize investigation graphs, detect emerging trends, and generate evidence-linked investigation packs.

> [!IMPORTANT]
> **Current implementation status:** Plan 02 — PostgreSQL, authentication, global/case RBAC, auditable case lifecycle, live case queries, administration reads, and authenticated frontend session UX — is implemented on `testing-codex`. Evidence ingestion and analytic features remain later-plan work. No page should be interpreted as containing real illicit-market or suspect data unless an authorized deployment has deliberately supplied it.

<p align="center">
  <img src="docs/screenshots/dashboard-overview.png" alt="DARKNETRA investigator overview dashboard" width="100%" />
</p>

The committed screenshot preserves the approved investigator-shell design. Runtime case and administration data now come from authenticated API boundaries rather than production fixture imports.

---

## Current capability status

| Capability | Status | Boundary |
|---|---|---|
| Investigator dashboard shell | ✅ Implemented | Responsive DARKNETRA navigation and protected workspace shell |
| PostgreSQL persistence | ✅ Implemented | Authoritative users, sessions, cases, memberships, roles, and audit events |
| Authentication | ✅ Implemented | Argon2 passwords, 15-minute access JWT, rotating 8-hour refresh session |
| Browser session security | ✅ Implemented | HttpOnly/SameSite cookies, strict origin checks, CSRF header validation |
| Login protection | ✅ Implemented | Generic failures, process throttle, five-failure/five-minute account lock |
| Bootstrap administrator | ✅ Implemented | One-time CLI creation; forced password change before normal mutations |
| Global and case RBAC | ✅ Implemented | Global role permission intersected with per-case membership role |
| Cross-case anti-enumeration | ✅ Implemented | Unknown and inaccessible case identifiers share the same 404 contract |
| Case lifecycle API | ✅ Implemented | Create, list, read, update, close, reopen, stable pagination |
| Case membership API | ✅ Implemented | Add/update/remove roles with last-owner and ADMIN-role invariants |
| Transactional audit | ✅ Implemented | Business mutation and append-only audit event commit together |
| Live case frontend | ✅ Implemented | Typed API client, explicit mapper, loading/empty/offline/access-denied states |
| Authenticated session UX | ✅ Implemented | Login, forced password change, logout, cache clearing, backend-unavailable state |
| Administration reads | ✅ Implemented | User list and role matrix sourced from backend policy truth |
| Real authorization E2E | ✅ Implemented | Disposable PostgreSQL + deterministic synthetic users/cases + Playwright |
| Evidence Vault | ⏳ Plan 03 | Not implemented in Plan 02 |
| Multilingual extraction | ⏳ Later plan | Not implemented |
| Alias/identity correlation | ⏳ Later plan | Not implemented |
| Neo4j NarcoGraph | ⏳ Later plan | Not implemented |
| Emerging-trend engine | ⏳ Later plan | Not implemented |
| Evidence-linked reports | ⏳ Later plan | Not implemented |
| Optional lawful collector | ⏳ Optional final stage | Disabled and unnecessary for the current core application |

---

## Core design rule

> **The evidence is the source of truth. AI may help explain evidence, but it must never silently become the evidence.**

Plan 02 does not ingest evidence or produce analytic findings. It establishes the authenticated, case-scoped, auditable foundation later plans must reuse.

```text
Authorized source material                         Later plans
        ↓
Evidence capture + integrity verification          Plan 03
        ↓
Extraction + explainable correlation               Plans 04–05
        ↓
Graph, trends, and evidence-linked reports         Plan 06

Authenticated identity + case authorization        Plan 02 ✅
Transactional audit + authoritative case IDs       Plan 02 ✅
```

---

## Architecture

```mermaid
flowchart LR
    I[Authorized investigator] --> W[Next.js 16 / React 19]
    W -->|credentialed /api/v1 requests| A[FastAPI]
    A --> AU[Authentication service]
    A --> P[Global + case policy]
    A --> C[Case and membership services]
    AU --> DB[(PostgreSQL 18)]
    P --> DB
    C --> DB
    C --> AE[Append-only audit event]
    AE --> DB

    A -. Plan 03 .-> EV[Evidence Vault]
    A -. Later plans .-> AN[Extraction + correlation]
    AN -. Later plans .-> G[(Neo4j NarcoGraph)]
```

### Authentication summary

- Passwords are hashed with Argon2.
- `darknetra_access` is an HttpOnly access cookie with a 15-minute JWT.
- `darknetra_refresh` is an HttpOnly, one-time rotating refresh cookie with an 8-hour server session.
- `darknetra_csrf` is a separate SameSite token copied into `X-CSRF-Token` for mutations.
- Refresh and CSRF values are stored only as hashes.
- Reuse of a rotated refresh token revokes the user's active sessions and emits an audit event.
- Tokens are never stored in `localStorage` or `sessionStorage`.

### Authorization summary

```text
effective case roles
  = roles stored on this case membership
    ∩ roles currently held globally by the user
```

A requested case permission must be granted by at least one effective role. A valid but inaccessible case UUID and an unknown UUID both return:

```json
{"detail":"resource not found"}
```

Full details are in [Authentication, authorization, and auditable case access](docs/architecture/authentication-authorization.md).

### Architecture decisions

- [ADR-0001: Frontend template baseline](docs/decisions/0001-frontend-template-baseline.md)
- [ADR-0002: UUID4 until an approved UUIDv7 implementation](docs/decisions/0002-use-uuid4-until-approved-uuidv7.md)

---

## Technology stack

### Frontend

- Next.js 16.3
- React 19.2
- TypeScript 5.9
- TanStack Query 5
- Tailwind CSS 4 and shadcn-derived components
- Biome
- Vitest + Testing Library
- Playwright

### Backend

- Python 3.12
- FastAPI 0.135
- Pydantic 2 and pydantic-settings
- SQLAlchemy 2 async + psycopg 3
- Alembic
- PostgreSQL 18
- Argon2id
- PyJWT/HS256
- pytest + pytest-asyncio
- Ruff

### Runtime and tooling

- Node.js 24
- pnpm 10.15.0
- uv 0.12.4
- Docker + Docker Compose v2
- GitHub Actions

---

## Repository structure

```text
darknetra/
├── apps/
│   ├── api/                     # FastAPI, SQLAlchemy models, Alembic, policy and services
│   └── web/                     # Next.js investigator application
├── docs/
│   ├── architecture/            # Runtime and security architecture
│   ├── decisions/               # ADRs
│   ├── screenshots/             # Generated interface screenshots
│   ├── superpowers/             # Approved designs and implementation plans
│   └── verification/            # Observed milestone evidence
├── infrastructure/docker/       # Non-root API and web images
├── scripts/                     # Smoke and deterministic test-fixture utilities
├── tests/repo/                  # Repository and deployment guardrails
├── docker-compose.yml           # Private application network and persistent PostgreSQL
├── docker-compose.dev.yml       # Loopback-only development ports
├── docker-compose.e2e.yml       # Isolated test database/profile
├── pyproject.toml / uv.lock     # Locked Python workspace
└── package.json / pnpm-lock.yaml
```

---

# Running DARKNETRA

## Prerequisites

### Docker path

- Git
- Docker Engine/Desktop
- Docker Compose v2

### Native development path

- Node.js 24.x
- pnpm 10.15.0 through Corepack
- Python 3.12.x
- uv 0.12.4
- PostgreSQL 18 or the Docker PostgreSQL service

---

## Docker quick start

The first authenticated start has three explicit operational steps: configure secrets, migrate PostgreSQL, and create the one-time administrator.

### 1. Configure the local environment

```bash
cp .env.example .env
```

Generate a 32-byte JWT signing key:

```bash
python - <<'PY'
import base64
import secrets
print(base64.b64encode(secrets.token_bytes(32)).decode())
PY
```

Place the printed value in `.env` as:

```text
DARKNETRA_JWT_SIGNING_KEY_B64=<generated value>
```

The local defaults use `http://localhost:3000` as `DARKNETRA_WEB_ORIGIN`. Keep the browser hostname consistent: a session issued for `localhost` should be used through `localhost`, not silently mixed with `127.0.0.1`.

### 2. Build images and start PostgreSQL

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml build api web
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres
```

Wait until PostgreSQL is healthy:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
```

### 3. Apply migrations

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
  -e PYTHONPATH=/app/apps/api \
  api uv run --no-sync alembic -c apps/api/alembic.ini upgrade head
```

### 4. Create the one-time administrator

Choose a strong temporary password through a secure local channel. The account will be forced to replace it immediately after login.

```bash
read -r -s DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD
export DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD

docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
  -e PYTHONPATH=/app/apps/api \
  -e DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD \
  api uv run --no-sync python -m darknetra_api.cli bootstrap-admin \
  --username administrator \
  --display-name "DARKNETRA Administrator"

unset DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD
```

The bootstrap command is intentionally one-time. A later attempt fails once an administrator exists.

### 5. Start the application

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --wait
```

Open:

```text
http://localhost:3000/auth/v2/login
```

API probes:

```bash
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
```

### 6. Inspect or stop the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
```

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans
```

Delete the development database volume only when a destructive reset is intentional:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v --remove-orphans
```

---

## Native development

### 1. Install locked workspaces

```bash
corepack enable
corepack prepare pnpm@10.15.0 --activate
pnpm install --frozen-lockfile
uv sync --all-packages --dev --frozen
```

### 2. Start PostgreSQL

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres
```

### 3. Export API configuration

```bash
export DARKNETRA_ENVIRONMENT=development
export DARKNETRA_BUILD_VERSION=local-dev
export DARKNETRA_DATABASE_URL='postgresql+psycopg://darknetra:darknetra-dev-only@127.0.0.1:5432/darknetra'
export DARKNETRA_WEB_ORIGIN='http://localhost:3000'
export DARKNETRA_JWT_SIGNING_KEY_B64='<base64 value decoding to 32 random bytes>'
```

### 4. Migrate and bootstrap

```bash
PYTHONPATH=apps/api uv run alembic -c apps/api/alembic.ini upgrade head
```

```bash
read -r -s DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD
export DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD
PYTHONPATH=apps/api uv run python -m darknetra_api.cli bootstrap-admin \
  --username administrator \
  --display-name 'DARKNETRA Administrator'
unset DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD
```

### 5. Start FastAPI

```bash
uv run uvicorn --app-dir apps/api darknetra_api.main:app \
  --reload --host 127.0.0.1 --port 8000
```

### 6. Start Next.js in another terminal

```bash
export DARKNETRA_API_BASE_URL='http://127.0.0.1:8000'
export NEXT_PUBLIC_DARKNETRA_API_BASE_URL='http://localhost:8000'
pnpm --filter @darknetra/web dev
```

Use `http://localhost:3000/auth/v2/login` when `DARKNETRA_WEB_ORIGIN` is `http://localhost:3000`.

---

## Environment variables

| Variable | Required | Purpose |
|---|---:|---|
| `DARKNETRA_ENVIRONMENT` | Yes | Environment name; local insecure-cookie relaxation is limited to explicit development/local origin |
| `DARKNETRA_BUILD_VERSION` | Yes | Version label returned by health endpoints |
| `DARKNETRA_DATABASE_URL` | Yes | PostgreSQL SQLAlchemy URL |
| `DARKNETRA_WEB_ORIGIN` | Yes | Exact browser origin for CORS and origin validation |
| `DARKNETRA_JWT_SIGNING_KEY_B64` | Auth required | Secret base64 value decoding to exactly 32 random bytes |
| `DARKNETRA_FIELD_KEY_V1_B64` | Sensitive fields / migration | Legacy v1 encryption key; runtime secret decoding to exactly 32 bytes |
| `DARKNETRA_FIELD_KEYRING_B64_JSON` | Sensitive fields / rotation | Runtime-secret JSON mapping retained key versions to 32-byte Base64 keys |
| `DARKNETRA_FIELD_BLIND_INDEX_KEY_B64` | Sensitive fields | Separate runtime-secret 32-byte HMAC key for equality indexes |
| `DARKNETRA_FIELD_ACTIVE_KEY_VERSION` | Sensitive fields | Non-secret version selected for new ciphertext; must exist in the runtime keyring |
| `DARKNETRA_POSTGRES_PASSWORD` | Docker | PostgreSQL development password interpolation |
| `DARKNETRA_API_BASE_URL` | Web server | Next.js server-to-API URL |
| `NEXT_PUBLIC_DARKNETRA_API_BASE_URL` | Browser | Browser-visible API URL; never a secret |
| `DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD` | Bootstrap only | One-time administrator password, consumed by the CLI and not printed |

> [!WARNING]
> Anything prefixed with `NEXT_PUBLIC_` is visible to browser JavaScript. Never place credentials, signing keys, case secrets, or investigator-sensitive configuration in a public variable.

---

## Stable API surface

Authentication:

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/refresh
POST /api/v1/auth/change-password
POST /api/v1/auth/logout
```

Cases and memberships:

```text
POST   /api/v1/cases
GET    /api/v1/cases
GET    /api/v1/cases/{case_id}
PATCH  /api/v1/cases/{case_id}
POST   /api/v1/cases/{case_id}/close
POST   /api/v1/cases/{case_id}/reopen
GET    /api/v1/cases/{case_id}/members
POST   /api/v1/cases/{case_id}/members
PATCH  /api/v1/cases/{case_id}/members/{user_id}
DELETE /api/v1/cases/{case_id}/members/{user_id}
```

Administration and audit:

```text
GET /api/v1/users
GET /api/v1/admin/roles
GET /api/v1/audit
```

Health:

```text
GET /api/v1/health/live
GET /api/v1/health/ready
```

---

## Testing and verification

### Complete backend suite

A PostgreSQL database migrated to the current head and these API variables are required:

```bash
uv run ruff check .
uv run pytest -q
uv run alembic -c apps/api/alembic.ini upgrade head
```

### Frontend suite

```bash
pnpm --filter @darknetra/web lint
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web test
pnpm --filter @darknetra/web build
```

### Synthetic browser regressions

```bash
pnpm --filter @darknetra/web exec playwright install chromium
pnpm --filter @darknetra/web test:e2e
```

This suite verifies protected online UI states plus an explicit backend-unavailable experience. It uses controlled browser route mocks for deterministic UI coverage.

### Real authentication and authorization browser regressions

```bash
pnpm --filter @darknetra/web test:e2e:real
```

This command expects the isolated real stack and test-only environment to be prepared. The canonical orchestration is `.github/workflows/plan02-task13.yml`; it:

1. creates a dedicated Compose project and disposable PostgreSQL volume;
2. applies Alembic migrations;
3. runs the fixture CLI, which refuses non-test databases/environments;
4. starts real API and web containers;
5. verifies bad login, normal login/logout, forced password change, and cross-case 404 equivalence;
6. tears down with `-v`.

### Compose and smoke

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null
bash scripts/smoke.sh
```

### Plan 02 verification evidence

The complete observed command outcomes, commit, UTC timestamp, migration head, real E2E result, and architecture deviation are recorded in:

```text
docs/verification/plan-02-api-auth-cases.md
```

Task-level diagnostic records remain under `docs/verification/plan02-task*.md`.

---

## Troubleshooting

### Login always fails after Docker starts

Confirm all three operational prerequisites were completed:

1. `DARKNETRA_JWT_SIGNING_KEY_B64` is present in `.env` and decodes to 32 bytes.
2. Alembic migrations were applied.
3. The one-time administrator was created.

Inspect API logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs api
```

### Login returns an origin rejection

Use the exact browser origin configured in `DARKNETRA_WEB_ORIGIN`. `localhost` and `127.0.0.1` are different origins.

### A mutation returns CSRF 403

Refresh the page/session and confirm requests pass through the typed frontend client. The API requires the current `darknetra_csrf` cookie value in `X-CSRF-Token` for authenticated mutations.

### An inaccessible case shows `Case unavailable`

That is intentional. DARKNETRA uses the same 404 response and frontend state for an unknown case and a case outside the current investigator's visibility.

### PostgreSQL schema errors

```bash
PYTHONPATH=apps/api uv run alembic -c apps/api/alembic.ini current
PYTHONPATH=apps/api uv run alembic -c apps/api/alembic.ini upgrade head
```

### Chromium is missing

```bash
pnpm --filter @darknetra/web exec playwright install --with-deps chromium
```

---

## Safety and legal boundary

DARKNETRA is an intelligence-triage and evidence-correlation platform for lawful, authorized use.

The project must not:

- purchase illegal drugs or facilitate a transaction;
- contact or negotiate with sellers;
- bypass encryption, authentication, or access controls;
- join private criminal services without lawful authorization;
- deploy malware;
- present an automated identity link or score as proof of identity or guilt;
- expose sensitive case data to unnecessary external services.

Lawful deployments may use public material, approved research archives, investigator-authorized sources, and lawfully obtained exports. Tests and demonstrations use controlled synthetic data.

DARKNETRA deliberately uses cautious workflow language such as **candidate**, **lead**, **pending review**, **analyst-confirmed**, **rejected**, **verified**, **warning**, **failed**, and **offline**. These are system states, not legal findings.

---

## Third-party attribution

The investigator interface adapts selected patterns and components from the MIT-licensed `arhamkhnz/next-shadcn-admin-dashboard`. Required attribution is retained in:

```text
LICENSES/next-shadcn-admin-dashboard-MIT.txt
```

Unrelated ecommerce, CRM, finance, academy, mail, chat, calendar, promotional, social-auth, and demo-only surfaces were removed rather than merely hidden. Third-party notices must be preserved regardless of DARKNETRA's eventual project license.

---

## Branch and development policy

- `main` is the stable branch; no direct feature development.
- `testing-codex` is the current integration branch.
- Read the approved design and implementation plan before changing a subsystem.
- Add the focused test first where practical and record the expected RED state.
- Do not claim a milestone from predicted results; run and commit the complete verification gate.
- Keep synthetic/test data explicitly labeled.
- Never replace an unimplemented backend with fabricated production output.

---

## Roadmap

```text
Plan 01  Foundation + Investigator Dashboard                 ✅ Complete
Plan 02  API + PostgreSQL + Auth + Users + Case RBAC         ✅ Complete
Plan 03  Evidence Vault + secure ingestion                    ⏳
Plan 04  Multilingual narcotics/entity extraction             ⏳
Plan 05  Activity detection + identity correlation            ⏳
Plan 06  Graph + trends + reports                             ⏳
Plan 07  Evaluation + offline finale hardening                ⏳
Optional lawful isolated collector                            ⏳ Last / optional
```

The optional collector is not a prerequisite for the core product. DARKNETRA's differentiator is the **evidence → extraction → explainable correlation → graph/trend → investigator report** workflow, supported by the authenticated and auditable case foundation now in place.

---

## Project principle

> **Find less noise. Preserve more evidence. Explain every link. Keep the investigator in control.**
