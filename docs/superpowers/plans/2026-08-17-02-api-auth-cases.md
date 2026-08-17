# DARKNETRA API, Authentication, RBAC, and Case Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Plan 01's fixture-backed user/case shell with a real FastAPI/PostgreSQL foundation, secure session authentication, case-scoped role-based authorization, auditable case lifecycle, and typed frontend queries while preserving the approved investigator UI interfaces.

**Architecture:** PostgreSQL becomes the authoritative source for identity, sessions, cases, memberships, and audit events. FastAPI exposes versioned `/api/v1` endpoints with explicit Pydantic contracts; the Next.js app consumes them through a small typed client/TanStack Query boundary. Global role permissions are intersected with per-case membership, and every state-changing action produces an audit record in the same database transaction.

**Tech Stack:** Python 3.12.x, FastAPI 0.135.x, Pydantic 2.x, pydantic-settings, SQLAlchemy 2.x async, Alembic, psycopg 3.x, PostgreSQL 18.x, Argon2id, PyJWT or python-jose-compatible JWT implementation, pytest, Hypothesis where useful, Next.js 16.3.x, React 19.2.x, TanStack Query 5.x, TypeScript 5.9.x, Docker Compose v2.

## Global Constraints

- Begin only after Plan 01 verification is committed and passing.
- Work on `testing-codex`; do not develop directly on `main`.
- PostgreSQL is authoritative. No Neo4j writes are introduced in this plan.
- Password hashes use Argon2id.
- Access token lifetime is 15 minutes.
- Rotating refresh-token lifetime is 8 hours by default; only a hash of each refresh token is stored server-side.
- Browser authentication tokens are delivered only with `HttpOnly`, `Secure` in non-local deployment, and `SameSite=Strict` cookies. Do not store access or refresh tokens in `localStorage` or `sessionStorage`.
- State-changing cookie-authenticated endpoints require CSRF protection.
- Repeated authentication failures are throttled/locked according to deterministic policy and audited.
- Bootstrap administrator must change the bootstrap password before normal administration actions.
- Global role permission is intersected with case membership. Cross-case enumeration must be prevented.
- Supported global roles: `ADMIN`, `CASE_OWNER`, `COLLECTOR`, `ANALYST`, `REVIEWER`, `AUDITOR`, `VIEWER`.
- Every mutation is authorized and audited; use transaction boundaries so business state and corresponding audit event cannot diverge.
- Error responses must not reveal whether inaccessible case IDs exist; use a consistent repository policy (`404` for case-scoped resources not visible to the requester in this plan).
- This plan does not ingest evidence or implement analytic features.

---

## Stable domain vocabulary

```python
from enum import StrEnum

class GlobalRole(StrEnum):
    ADMIN = "ADMIN"
    CASE_OWNER = "CASE_OWNER"
    COLLECTOR = "COLLECTOR"
    ANALYST = "ANALYST"
    REVIEWER = "REVIEWER"
    AUDITOR = "AUDITOR"
    VIEWER = "VIEWER"

class CaseStatus(StrEnum):
    OPEN = "OPEN"
    REVIEW = "REVIEW"
    CLOSED = "CLOSED"

class CaseSensitivity(StrEnum):
    STANDARD = "STANDARD"
    RESTRICTED = "RESTRICTED"
```

Case membership carries one or more case roles chosen from the same role vocabulary except `ADMIN`; global `ADMIN` bypasses membership checks only for explicitly administrative operations and still produces audit records.

---

### Task 1: Add PostgreSQL service, SQLAlchemy async engine, and Alembic baseline

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.dev.yml`
- Modify: `.env.example`
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/script.py.mako`
- Create: `apps/api/darknetra_api/db/base.py`
- Create: `apps/api/darknetra_api/db/session.py`
- Create: `apps/api/tests/integration/test_database_health.py`

**Interfaces:**
- Produces `get_db_session() -> AsyncIterator[AsyncSession]` and `Base` declarative model base.
- Compose service name: `postgres`; database: `darknetra`; non-secret dev username: `darknetra`; password supplied by environment.

- [ ] **Step 1: Write a failing integration test for database connectivity**

```python
import sqlalchemy as sa

from darknetra_api.db.session import async_session_factory


async def test_database_connection() -> None:
    async with async_session_factory() as session:
        result = await session.execute(sa.text("select 1"))
        assert result.scalar_one() == 1
```

Mark integration tests explicitly and configure pytest asyncio mode.

- [ ] **Step 2: Add runtime dependencies**

Add to `apps/api/pyproject.toml`:

```toml
"sqlalchemy[asyncio]>=2.0,<3",
"alembic>=1.16,<2",
"psycopg[binary,pool]>=3.2,<4",
```

Run `uv lock` and `uv sync --all-packages --dev`.

- [ ] **Step 3: Add PostgreSQL to Compose with health check and named volume**

Use `postgres:18` for development with a release digest pinned before final release. Do not publish port 5432 in base Compose; expose it only in `docker-compose.dev.yml` if developers need host access.

Required health check:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
  interval: 5s
  timeout: 3s
  retries: 10
```

API must depend on healthy Postgres only after this task.

- [ ] **Step 4: Implement async SQLAlchemy session boundary**

`session.py` must create the engine from `DARKNETRA_DATABASE_URL`, use `pool_pre_ping=True`, and expose an async sessionmaker with `expire_on_commit=False`. FastAPI dependency must always close the session.

- [ ] **Step 5: Initialize Alembic against shared metadata**

`alembic/env.py` imports `Base.metadata` and uses the application database URL. Never import a live FastAPI app to run migrations.

- [ ] **Step 6: Run database integration test against Compose Postgres**

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres
uv run pytest apps/api/tests/integration/test_database_health.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit database foundation**

```bash
git add apps/api docker-compose.yml docker-compose.dev.yml .env.example uv.lock
git commit -m "feat: add PostgreSQL persistence foundation"
```

---

### Task 2: Define identity, session, case, membership, and audit models

**Files:**
- Create: `apps/api/darknetra_api/models/enums.py`
- Create: `apps/api/darknetra_api/models/user.py`
- Create: `apps/api/darknetra_api/models/auth_session.py`
- Create: `apps/api/darknetra_api/models/case.py`
- Create: `apps/api/darknetra_api/models/case_membership.py`
- Create: `apps/api/darknetra_api/models/audit.py`
- Create: `apps/api/darknetra_api/models/__init__.py`
- Create: first Alembic revision under `apps/api/alembic/versions/`.
- Create: `apps/api/tests/integration/test_schema_constraints.py`

**Interfaces:**
- Produces tables `users`, `auth_sessions`, `cases`, `case_memberships`, `case_membership_roles`, `audit_events`.
- UUID primary keys generated application-side with UUIDv7 if an approved implementation is available; otherwise UUID4 is acceptable for this plan and must be documented rather than inventing a custom UUID algorithm.

- [ ] **Step 1: Write failing schema-constraint tests**

Cover unique normalized username, disabled-user flag, unique case code, membership uniqueness `(case_id,user_id)`, and append-only audit-event ORM behavior.

- [ ] **Step 2: Implement enums exactly as the stable domain vocabulary**

Do not store display labels as enum values.

- [ ] **Step 3: Implement SQLAlchemy models with UTC timestamps**

Required user fields:

```text
id, username, username_normalized, display_name, password_hash,
global_roles, is_active, must_change_password, failed_login_count,
locked_until, created_at, updated_at
```

Required case fields:

```text
id, case_code, title, status, sensitivity, owner_user_id,
source_authority_summary, created_at, updated_at, closed_at
```

`source_authority_summary` is a short non-secret description in this plan; sensitive authority references are introduced with encryption policy later. Do not store secrets in it.

Required audit fields:

```text
id, actor_user_id nullable for bootstrap/system, event_type,
resource_type, resource_id, case_id nullable, request_id,
metadata_json, created_at
```

- [ ] **Step 4: Generate and inspect Alembic migration**

Run:

```bash
uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "create identity and case tables"
```

Open the generated revision and verify it creates only intended tables/indexes/constraints. Edit generated migration if naming/defaults are incorrect.

- [ ] **Step 5: Apply migration and run schema tests**

```bash
uv run alembic -c apps/api/alembic.ini upgrade head
uv run pytest apps/api/tests/integration/test_schema_constraints.py -v
```

- [ ] **Step 6: Verify downgrade on disposable test database, then restore head**

```bash
uv run alembic -c apps/api/alembic.ini downgrade base
uv run alembic -c apps/api/alembic.ini upgrade head
```

Expected: both exit 0 on a disposable development database.

- [ ] **Step 7: Commit schema**

```bash
git add apps/api
git commit -m "feat: define identity case and audit schema"
```

---

### Task 3: Implement password hashing and bootstrap administrator flow

**Files:**
- Create: `apps/api/darknetra_api/security/passwords.py`
- Create: `apps/api/darknetra_api/services/bootstrap.py`
- Create: `apps/api/darknetra_api/cli.py`
- Create: `apps/api/tests/unit/test_passwords.py`
- Create: `apps/api/tests/integration/test_bootstrap_admin.py`

**Interfaces:**
- `hash_password(password: str) -> str`
- `verify_password(password: str, encoded_hash: str) -> bool`
- CLI: `python -m darknetra_api.cli bootstrap-admin --username <name>` reads password from secure prompt or environment intended for one-time bootstrap and never prints it.

- [ ] **Step 1: Write failing password tests**

Verify correct password, wrong password, two hashes of same password differ because of salt, and hash string identifies Argon2id.

- [ ] **Step 2: Add Argon2 dependency and implement password helper**

Use `argon2-cffi` PasswordHasher with Argon2id defaults. Do not invent cryptographic primitives.

- [ ] **Step 3: Write failing bootstrap idempotency test**

The first bootstrap creates an active `ADMIN` with `must_change_password=True`; the second attempt for the same normalized username must fail without replacing the hash.

- [ ] **Step 4: Implement bootstrap service and CLI**

Bootstrap audit event must use `event_type="ADMIN_BOOTSTRAPPED"` and never include plaintext password/hash in metadata.

- [ ] **Step 5: Run tests and security grep**

```bash
uv run pytest apps/api/tests/unit/test_passwords.py apps/api/tests/integration/test_bootstrap_admin.py -v
rg -n "password.*print|print.*password" apps/api/darknetra_api || true
```

- [ ] **Step 6: Commit**

```bash
git add apps/api uv.lock
git commit -m "feat: add secure administrator bootstrap"
```

---

### Task 4: Implement rotating cookie session authentication and CSRF protection

**Files:**
- Create: `apps/api/darknetra_api/security/tokens.py`
- Create: `apps/api/darknetra_api/security/csrf.py`
- Create: `apps/api/darknetra_api/services/auth.py`
- Create: `apps/api/darknetra_api/schemas/auth.py`
- Create: `apps/api/darknetra_api/routes/auth.py`
- Create: `apps/api/tests/unit/test_tokens.py`
- Create: `apps/api/tests/integration/test_auth_flow.py`

**Interfaces:**
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/me`
- Access token 15 min; refresh token 8 h; refresh rotates every successful refresh.

- [ ] **Step 1: Write token tests before implementation**

Test expiration claims, token type separation, issuer/audience validation, random refresh token entropy, and hash-only refresh persistence.

- [ ] **Step 2: Implement token primitives using a maintained JWT library and `secrets.token_urlsafe` for opaque refresh tokens**

Access JWT payload may contain only stable user ID, token type, issued/expiry times, issuer/audience, and a session ID. Do not put permissions or sensitive case data in the token; authorization reads current DB state.

- [ ] **Step 3: Write failing end-to-end API auth-flow test**

Test login -> me -> refresh rotates -> old refresh rejected -> logout invalidates session. Inspect response headers to verify cookies are HttpOnly and SameSite Strict. In local HTTP tests, `Secure` may be environment-configurable; production configuration must force it.

- [ ] **Step 4: Implement login throttling policy**

Policy in this plan:

```text
5 consecutive failed attempts -> 5 minute lock
successful login -> failed count reset
locked account -> generic authentication failure response
all lock/unlock/login-success/login-failure events -> audit
```

Use UTC database timestamps; do not sleep in request handlers.

- [ ] **Step 5: Implement CSRF double-submit or server-session-bound token**

Whichever approach is chosen, tests must prove a state-changing request with valid auth cookie but absent/incorrect CSRF token is rejected. Do not exempt mutation endpoints for frontend convenience.

- [ ] **Step 6: Implement forced bootstrap password change**

A user with `must_change_password=True` may access `/auth/me`, `/auth/change-password`, `/auth/logout`, but administrative/case mutation dependencies reject normal operations until password change succeeds.

- [ ] **Step 7: Run auth tests**

```bash
uv run pytest apps/api/tests/unit/test_tokens.py apps/api/tests/integration/test_auth_flow.py -v
```

- [ ] **Step 8: Commit**

```bash
git add apps/api
git commit -m "feat: add rotating secure session authentication"
```

---

### Task 5: Implement authorization policy engine with case-scope intersection

**Files:**
- Create: `apps/api/darknetra_api/authz/permissions.py`
- Create: `apps/api/darknetra_api/authz/policy.py`
- Create: `apps/api/darknetra_api/dependencies/auth.py`
- Create: `apps/api/tests/unit/test_policy.py`
- Create: `apps/api/tests/integration/test_cross_case_authorization.py`

**Interfaces:**
- `Permission` string enum.
- `authorize_global(user, permission) -> None` raises domain authorization error.
- `authorize_case(user, case_id, permission, session) -> None` enforces role + membership.

- [ ] **Step 1: Define permission vocabulary and role map in tests first**

Permissions for this plan:

```text
CASE_CREATE
CASE_READ
CASE_UPDATE
CASE_CLOSE
CASE_REOPEN
CASE_MEMBERSHIP_MANAGE
USER_READ
USER_MANAGE
ROLE_READ
AUDIT_READ
SYSTEM_HEALTH_READ
```

Tests must explicitly define expected role grants; do not infer permissions from UI navigation.

- [ ] **Step 2: Implement immutable role-permission mapping**

Keep it in code for Plan 02. Database-customizable roles are not introduced because auditability and safety are more important than a role-builder feature during the hackathon.

- [ ] **Step 3: Implement FastAPI current-user and authorization dependencies**

Every dependency returns domain objects, not raw token claims.

- [ ] **Step 4: Write cross-case enumeration tests**

Create two cases and two analysts. Requests by analyst A for analyst B's inaccessible case ID must return the same 404 response shape as a random unknown case ID.

- [ ] **Step 5: Run policy and integration tests**

```bash
uv run pytest apps/api/tests/unit/test_policy.py apps/api/tests/integration/test_cross_case_authorization.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/api
git commit -m "feat: enforce case scoped authorization"
```

---

### Task 6: Implement case lifecycle API and transactional audit events

**Files:**
- Create: `apps/api/darknetra_api/schemas/cases.py`
- Create: `apps/api/darknetra_api/repositories/cases.py`
- Create: `apps/api/darknetra_api/services/cases.py`
- Create: `apps/api/darknetra_api/services/audit.py`
- Create: `apps/api/darknetra_api/routes/cases.py`
- Create: `apps/api/tests/integration/test_case_lifecycle.py`

**Interfaces:**
- `POST /api/v1/cases`
- `GET /api/v1/cases`
- `GET /api/v1/cases/{case_id}`
- `PATCH /api/v1/cases/{case_id}`
- `POST /api/v1/cases/{case_id}/close`
- `POST /api/v1/cases/{case_id}/reopen`

- [ ] **Step 1: Write lifecycle tests first**

Cover create, list only visible cases, retrieve, update allowed fields, close with timestamp, prohibit invalid double-close behavior, reopen with audit, and reject unauthorized access.

- [ ] **Step 2: Define strict Pydantic request/response schemas**

Create request fields:

```text
case_code: uppercase letters/digits/hyphen, 3..40
 title: 3..200 characters
 sensitivity: STANDARD|RESTRICTED
 source_authority_summary: 1..500 characters
```

Trim input; never silently truncate.

- [ ] **Step 3: Implement repository queries with visibility filters**

List query must filter in SQL rather than loading every case then filtering in Python.

- [ ] **Step 4: Implement service transaction boundary**

For each mutation:

```text
validate -> authorize -> mutate -> append audit event -> commit once
```

If audit insert fails, business mutation must roll back.

- [ ] **Step 5: Add pagination contract**

Use `limit` default 25 max 100 and cursor or stable offset pagination. If offset pagination is chosen for hackathon simplicity, sort by `(updated_at DESC, id DESC)` and document it; do not return unbounded case lists.

- [ ] **Step 6: Run lifecycle tests**

```bash
uv run pytest apps/api/tests/integration/test_case_lifecycle.py -v
```

- [ ] **Step 7: Commit**

```bash
git add apps/api
git commit -m "feat: add auditable case lifecycle API"
```

---

### Task 7: Implement membership-management API

**Files:**
- Create: `apps/api/darknetra_api/schemas/memberships.py`
- Create: `apps/api/darknetra_api/repositories/memberships.py`
- Create: `apps/api/darknetra_api/services/memberships.py`
- Create: `apps/api/darknetra_api/routes/memberships.py`
- Create: `apps/api/tests/integration/test_case_memberships.py`

**Interfaces:**
- `GET /api/v1/cases/{case_id}/members`
- `POST /api/v1/cases/{case_id}/members`
- `PATCH /api/v1/cases/{case_id}/members/{user_id}`
- `DELETE /api/v1/cases/{case_id}/members/{user_id}`

- [ ] **Step 1: Write tests for owner/member invariants**

Required invariants:

```text
- case owner always retains CASE_OWNER membership;
- cannot remove the last CASE_OWNER;
- ADMIN may repair memberships but action is audited;
- duplicate member insert is rejected idempotently/cleanly;
- membership roles cannot include ADMIN;
- inaccessible case still returns 404.
```

- [ ] **Step 2: Implement schemas and service invariants**

Use sets/unique rows for roles. Do not store comma-separated role strings.

- [ ] **Step 3: Append audit events for add/update/remove**

Audit metadata contains affected user ID and role names only; no auth secrets.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest apps/api/tests/integration/test_case_memberships.py -v
git add apps/api
git commit -m "feat: add case membership management"
```

---

### Task 8: Implement read-only user/role/audit APIs needed by Plan 01 administration UI

**Files:**
- Create: `apps/api/darknetra_api/schemas/users.py`
- Create: `apps/api/darknetra_api/routes/users.py`
- Create: `apps/api/darknetra_api/routes/admin.py`
- Create: `apps/api/darknetra_api/routes/audit.py`
- Create: `apps/api/tests/integration/test_admin_reads.py`

**Interfaces:**
- `GET /api/v1/users` authorized for ADMIN and case-owner user-picker use according to policy.
- `GET /api/v1/admin/roles` returns fixed role/permission matrix.
- `GET /api/v1/audit` requires `AUDIT_READ` and supports case/resource/event/time filters with pagination.

- [ ] **Step 1: Write authorization and redaction tests**

User list response exposes user ID, display name, username, active state, global roles; never password hashes, token hashes, failure counters, or lock internals unless a dedicated admin need is justified.

- [ ] **Step 2: Implement fixed role-matrix endpoint from the same policy source used for enforcement**

Do not duplicate permission mappings in route code.

- [ ] **Step 3: Implement paginated audit query**

Sort newest first. Metadata is returned only to authorized auditors/admins; later sensitive audit encryption policy can refine fields.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest apps/api/tests/integration/test_admin_reads.py -v
git add apps/api
git commit -m "feat: expose administration read APIs"
```

---

### Task 9: Add frontend typed API client and TanStack Query provider

**Files:**
- Modify/create retained provider composition in `apps/web/src/app/**`.
- Create: `apps/web/src/lib/api/client.ts`
- Create: `apps/web/src/lib/api/errors.ts`
- Create: `apps/web/src/lib/api/auth.ts`
- Create: `apps/web/src/lib/api/cases.ts`
- Create: `apps/web/src/lib/api/admin.ts`
- Create: `apps/web/src/lib/query/query-provider.tsx`
- Create frontend tests under `apps/web/src/lib/api/__tests__/`.

**Interfaces:**
- One `apiFetch<T>()` handles credentials, JSON parsing, CSRF header for mutations, and typed errors.
- TanStack Query keys are centralized in `apps/web/src/lib/query/keys.ts`.

- [ ] **Step 1: Write failing client tests**

Cover success JSON, 401, 403/404, 422 validation body, 500, network error, request abort, and CSRF inclusion on mutation.

- [ ] **Step 2: Implement `ApiError` with status/code/details**

Do not parse errors by string matching in page components.

- [ ] **Step 3: Implement `apiFetch` with `credentials: "include"`**

Access/refresh cookies remain browser-managed and inaccessible to JavaScript. CSRF token may be obtained from a non-HttpOnly dedicated cookie or `/auth/me` contract according to backend implementation; choose one and test it.

- [ ] **Step 4: Add TanStack Query provider**

Use conservative retry policy: do not retry 401/403/404/422 automatically; retry transient network/5xx a small bounded number of times.

- [ ] **Step 5: Run frontend API tests**

```bash
pnpm --filter @darknetra/web test -- src/lib/api
```

- [ ] **Step 6: Commit**

```bash
git add apps/web pnpm-lock.yaml
git commit -m "feat: add typed authenticated frontend API client"
```

---

### Task 10: Replace case fixtures with live queries while preserving Plan 01 component interfaces

**Files:**
- Modify: `apps/web/src/features/cases/types.ts`
- Create: `apps/web/src/features/cases/queries.ts`
- Modify: `apps/web/src/features/cases/case-table.tsx`
- Modify: case route pages/layout.
- Create: component/query tests.

**Interfaces:**
- Preserve UI `CaseSummary` shape through an explicit API-to-view mapper rather than making UI components depend directly on transport response casing/fields.

- [ ] **Step 1: Write mapper tests first**

Test timezone strings, status/sensitivity/source fields, missing optional counts (Plan 02 backend may return zero for evidence/alerts until later plans), and unknown enum rejection.

- [ ] **Step 2: Implement `mapCaseSummary` and queries**

Queries:

```text
useCases(filters)
useCase(caseId)
useCaseMembers(caseId)
```

- [ ] **Step 3: Replace fixture imports in pages**

Retain explicit loading, empty, error, stale, and access-denied behavior. Unknown/inaccessible case must not fall back to fixture data.

- [ ] **Step 4: Keep fixture module only for tests/story-like development if still useful**

Production routes must not import fixture data after this task.

- [ ] **Step 5: Run tests/build and commit**

```bash
pnpm --filter @darknetra/web test
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web build
git add apps/web
git commit -m "feat: connect cases dashboard to authenticated API"
```

---

### Task 11: Implement login, forced password-change, logout, and authenticated shell states

**Files:**
- Adapt retained auth route/page from upstream under `apps/web/src/app/**/auth/**`.
- Create: `apps/web/src/features/auth/login-form.tsx`
- Create: `apps/web/src/features/auth/change-password-form.tsx`
- Create: `apps/web/src/features/auth/session-gate.tsx`
- Create tests.

**Interfaces:**
- `SessionGate` states: checking, unauthenticated, must-change-password, authenticated, backend-unavailable.

- [ ] **Step 1: Write form tests**

Verify labels/autocomplete attributes, generic invalid-credential message, no password value persistence, keyboard submission, and disabled state during mutation.

- [ ] **Step 2: Implement login with cookie-backed API**

Never log credential fields. Do not add social login/OAuth buttons unless an actual identity provider is configured in a later plan.

- [ ] **Step 3: Implement forced password-change path**

Authenticated bootstrap user cannot reach normal dashboard until password change succeeds. Preserve logout access.

- [ ] **Step 4: Implement logout and cache clearing**

On successful logout, clear TanStack Query cache before redirecting to login.

- [ ] **Step 5: Run auth component/E2E tests and commit**

```bash
pnpm --filter @darknetra/web test -- src/features/auth
pnpm --filter @darknetra/web test:e2e
git add apps/web
git commit -m "feat: add authenticated investigator session UX"
```

---

### Task 12: Connect Administration role matrix and user reads to backend policy source

**Files:**
- Modify: `apps/web/src/features/admin/roles/role-permission-matrix.tsx`
- Create: `apps/web/src/features/admin/roles/queries.ts`
- Create: `apps/web/src/features/admin/users/user-table.tsx`
- Create: `apps/web/src/features/admin/users/queries.ts`
- Modify admin routes.

**Interfaces:**
- Role matrix renders `/api/v1/admin/roles` response; no duplicated frontend permission truth.

- [ ] **Step 1: Write tests proving role matrix data comes from query boundary**

Mock endpoint response with one permission change and verify UI reflects server data, demonstrating frontend does not hard-code enforcement truth.

- [ ] **Step 2: Implement user list with safe fields only**

No password/session/lock internals displayed.

- [ ] **Step 3: Implement role-aware 403/404 UI states**

Unauthorized user sees a clear access-denied page, not a broken blank table.

- [ ] **Step 4: Run and commit**

```bash
pnpm --filter @darknetra/web test -- src/features/admin
pnpm --filter @darknetra/web build
git add apps/web
git commit -m "feat: connect administration reads to policy API"
```

---

### Task 13: Add backend/frontend authorization and authentication E2E regression suite

**Files:**
- Create: `apps/web/e2e/auth.spec.ts`
- Create: `apps/web/e2e/case-authorization.spec.ts`
- Create: `scripts/create_e2e_fixture.py`
- Modify Playwright config/Compose test profile as needed.

**Interfaces:**
- Deterministic test users/cases created only in isolated E2E database.

- [ ] **Step 1: Implement fixture creation CLI with synthetic credentials from environment**

It must refuse to run unless `DARKNETRA_ENVIRONMENT=test` and database name clearly identifies test scope. It creates fictional users/cases and outputs IDs, not passwords.

- [ ] **Step 2: Write E2E auth test**

Covers login, dashboard, logout, bad password, forced change for bootstrap-style user.

- [ ] **Step 3: Write cross-case browser test**

Analyst A navigating directly to Analyst B's case ID must receive the same not-found experience as a random unknown ID.

- [ ] **Step 4: Run E2E suite against isolated stack**

Use a dedicated Compose project name and disposable database volume. Tear down with `-v` after run.

- [ ] **Step 5: Commit**

```bash
git add apps/web scripts
git commit -m "test: cover authenticated case authorization end to end"
```

---

### Task 14: Final Plan 02 verification and documentation

**Files:**
- Modify: `README.md`
- Create: `docs/verification/plan-02-api-auth-cases.md`
- Create or update: `docs/architecture/authentication-authorization.md`

**Interfaces:**
- Produces documented stable APIs for Plan 03 evidence work.

- [ ] **Step 1: Document authentication and authorization model**

Include cookie/session design, token lifetimes, refresh rotation, CSRF mechanism, lockout policy, role/permission source, case-membership intersection, 404 anti-enumeration policy, and audit transaction rule.

- [ ] **Step 2: Run complete fresh verification**

```bash
uv run ruff check .
uv run pytest -q
uv run alembic -c apps/api/alembic.ini upgrade head
pnpm --filter @darknetra/web lint
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web test
pnpm --filter @darknetra/web build
pnpm --filter @darknetra/web test:e2e
docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null
bash scripts/smoke.sh
```

- [ ] **Step 3: Record observed results rather than predicted counts**

Verification document includes actual commit SHA, UTC time, migration head, command exit statuses, and any architecture deviations with ADR links.

- [ ] **Step 4: Commit verification**

```bash
git add README.md docs/verification/plan-02-api-auth-cases.md docs/architecture/authentication-authorization.md
git commit -m "docs: verify authentication and case foundation"
```

---

## Plan 02 Definition of Done

- PostgreSQL is the real authoritative persistence layer for users, sessions, cases, memberships, and audit events.
- Alembic upgrade/downgrade path is tested on a disposable database.
- Argon2id password hashing is verified.
- Access sessions and rotating refresh tokens follow the specified lifetimes and cookie constraints.
- Refresh tokens are stored only as hashes and old tokens fail after rotation.
- CSRF protection is proven by negative tests.
- Five consecutive failed logins trigger the specified temporary lock and audit events.
- Bootstrap admin must change password before normal privileged work.
- Global-role permission and case membership are both enforced.
- Cross-case resource IDs do not reveal existence.
- Case lifecycle and membership changes are transactionally audited.
- Frontend production routes no longer depend on case/admin fixtures.
- Login/logout/session expiry/backend-unavailable states are user-friendly and explicit.
- Role matrix is rendered from backend policy truth.
- Full backend/frontend test, lint, type, build, E2E, migration, and Docker smoke verification is recorded.

## Plan 03 handoff contract

Plan 03 may rely on authenticated current-user context, case authorization dependencies, authoritative case IDs, transactional audit service, async SQLAlchemy session factory, Alembic migrations, typed frontend API client, and case-scoped route shell. Evidence ingestion must reuse these boundaries rather than bypassing them.