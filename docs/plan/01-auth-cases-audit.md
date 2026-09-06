# Plan 01 — Auth, RBAC, service tokens, cases, audit

Milestone M1 · Owner A · Depends on 00 · Ports the proven design from `jrdevadattan/darknetra` Plan 02 into the new backend.

**Goal.** Authenticated, case-scoped, auditable access: password login with cookies and CSRF, refresh rotation with reuse detection, lockout, bootstrap admin, service tokens with scopes, global and case roles, case lifecycle with a source policy, membership invariants, a derived timeline, and an append-only audit trail with middleware.

**Architecture.** `auth/` owns credentials and sessions; `authz/` owns the permission matrix and the `require(...)` dependencies; `cases/` owns case state; `audit/` owns `record()` and the middleware. Unknown and inaccessible cases both raise `NotFound` (anti-enumeration).

---

## Files

```
darknetra/auth/
├── models.py          User, Session, ApiToken (already created in 00; add relationships)
├── passwords.py       argon2id hash/verify (time_cost=3, memory_cost=64 MiB, parallelism=2)
├── jwt.py             encode/decode HS256; claims sub, sid, role, iat, exp, typ="access"
├── cookies.py         set/clear darknetra_access, darknetra_refresh, darknetra_csrf
├── service.py         login, refresh, logout, change_password, lockout, token issue/verify
├── tokens.py          service tokens: create (returns plaintext once), verify, scopes
├── cli.py             `python -m darknetra.auth.cli bootstrap-admin --username ... --display-name ...`
darknetra/authz/
├── permissions.py     Permission enum + matrix
├── deps.py            current_actor(), require(permission, case_scoped=True), case_visible()
darknetra/cases/
├── models.py          Case, CaseMembership
├── codes.py           next_case_code(session) → "CHD-2026-0001"
├── policy.py          SourcePolicy pydantic model + defaults + validation
├── service.py         create, get_visible, update, close/reopen/archive, members, timeline, summary
darknetra/audit/
├── models.py          AuditEvent
├── service.py         record(session, *, actor, action, target_type, target_id, case_id=None, thread_id=None, detail=None, result_hash=None)
├── middleware.py       records every mutating request (method, route, status, actor, case id if in path)
darknetra/crypto/
└── fields.py          encrypt/decrypt (AES-256-GCM envelope, key version), blind_index(value) = HMAC-SHA256 truncated
alembic/versions/0002_auth_cases.py   (only if 0001 lacks any column from plan 12)
tests/unit/test_passwords.py test_jwt.py test_permissions.py test_case_codes.py test_fields.py
tests/integration/test_auth_flow.py test_lockout.py test_refresh_rotation.py test_tokens.py test_cases.py test_members.py test_audit.py test_anti_enumeration.py
```

---

## Interfaces

### Actor

```python
@dataclass(frozen=True)
class Actor:
    kind: Literal["USER", "TOKEN", "SYSTEM"]
    id: uuid.UUID | None
    global_role: GlobalRole | None          # ADMIN | INVESTIGATOR | VIEWER
    scopes: frozenset[str]                  # for tokens
    session_id: uuid.UUID | None
```

`current_actor()` reads the access cookie (users) or `Authorization: Bearer dk_…` (tokens). Both may be present; the cookie wins for browser routes, the bearer for API routes; never mix silently.

### Permissions

```python
class Permission(StrEnum):
    CASE_CREATE, CASE_VIEW, CASE_EDIT, CASE_CLOSE, CASE_ARCHIVE, CASE_MANAGE_MEMBERS, CASE_MANAGE_POLICY,
    EVIDENCE_UPLOAD, EVIDENCE_VIEW, EVIDENCE_VIEW_ORIGINAL, EVIDENCE_RELEASE_QUARANTINE,
    THREAD_RUN, THREAD_VIEW, DECIDE, FINDING_EDIT,
    WATCHLIST_MANAGE, ALERT_HANDLE, REPORT_GENERATE, EXPORT,
    AUDIT_VIEW_CASE, AUDIT_VIEW_GLOBAL, ADMIN_USERS, ADMIN_SETTINGS, ADMIN_TAXONOMY, TOOLS_HEALTH
```

Matrix (case role × permission); global role caps it: `effective = case_role_perms ∩ global_role_perms`.

| Permission | OWNER | LEAD | ANALYST | VIEWER |
|---|---|---|---|---|
| CASE_VIEW, EVIDENCE_VIEW, THREAD_VIEW | ✓ | ✓ | ✓ | ✓ |
| EVIDENCE_UPLOAD, THREAD_RUN, WATCHLIST_MANAGE, ALERT_HANDLE, REPORT_GENERATE | ✓ | ✓ | ✓ | — |
| DECIDE, FINDING_EDIT, EVIDENCE_VIEW_ORIGINAL | ✓ | ✓ | ✓ | — |
| EVIDENCE_RELEASE_QUARANTINE, EXPORT, AUDIT_VIEW_CASE | ✓ | ✓ | — | — |
| CASE_EDIT, CASE_CLOSE, CASE_MANAGE_MEMBERS, CASE_MANAGE_POLICY | ✓ | ✓ | — | — |
| CASE_ARCHIVE | ✓ | — | — | — |

Global: ADMIN has everything plus ADMIN_* and AUDIT_VIEW_GLOBAL and sees all cases; INVESTIGATOR has CASE_CREATE and case-scoped permissions through memberships; VIEWER has no CASE_CREATE and is capped at VIEWER in any case. Token scopes map to permissions: `cases:read → CASE_VIEW, EVIDENCE_VIEW, THREAD_VIEW`; `threads:run → THREAD_RUN`; `alerts:read → ALERT view`; `monitor:run → WATCHLIST_MANAGE`.

### Dependencies

```python
def require(perm: Permission) -> Callable[..., Awaitable[Actor]]   # for global routes
def require_case(perm: Permission) -> Callable[..., Awaitable[tuple[Actor, Case]]]   # loads case; NotFound if invisible
```

### Cookies and CSRF

- `darknetra_access` (JWT, HttpOnly, SameSite=Lax, Secure in production, Path=/api, Max-Age=900)
- `darknetra_refresh` (opaque 32 bytes hex, HttpOnly, Path=/api/v1/auth, Max-Age=28800)
- `darknetra_csrf` (32 bytes hex, not HttpOnly, SameSite=Lax); mutations require header `X-CSRF-Token` equal to the cookie, and `Origin` equal to `settings.web_origin`. Bearer-token requests skip CSRF.
- Refresh and CSRF values are stored only as SHA-256 hashes on `sessions`.

### Auth service

- `login(username, password, ip, ua)`: constant-time path; generic failure message; `failed_logins` increment; lock 5 minutes after 5 failures; on success reset counters, create session, issue cookies; audit `auth.login`.
- `refresh(refresh_cookie)`: look up by hash; if `revoked_at` set or already rotated → **reuse detected**: revoke all sessions of the user, audit `auth.refresh_reuse`, 401. Otherwise rotate (new refresh + csrf, same session id), extend expiry.
- `logout`: revoke session, clear cookies, audit.
- `change_password`: verify current, hash new (min 12 chars), revoke other sessions, clear `must_change_password`.
- `bootstrap-admin` CLI: refuses if any ADMIN exists; password from env `DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD`; sets `must_change_password=true`. While that flag is set, only `/auth/me`, `/auth/change-password`, `/auth/logout` are allowed.

### Service tokens

- `POST /auth/tokens {name, scopes[], case_id?, expires_in_days?}` → `{id, token: "dk_<48 hex>", scopes, expires_at}` (plaintext only once). Stored as SHA-256. `last_used_at` updated at most once per minute.
- Verification: constant-time compare of hash; expired or revoked → 401 `FORBIDDEN`? No: 401 with `code: "UNAUTHENTICATED"` (add to errors).

### Field encryption

`crypto/fields.py`: `encrypt(plaintext: str, aad: str) -> bytes` = `key_version(1) || nonce(12) || ciphertext||tag`; `decrypt(blob, aad)`; `blind_index(value) -> str` = hex(HMAC-SHA256(key, normalised value))[:32]. AAD is `"<table>:<column>"`. Used by cases (`authority_ref_enc`) and evidence (`locator_enc`, plan 02).

### Cases

- `POST /cases {title, scope_notes?, authority_ref?, source_policy?}` → Case; creator becomes OWNER; code from `codes.next_case_code` (sequence per year, `CHD-YYYY-NNNN`).
- `SourcePolicy` defaults: `allowed_source_classes=["SYNTHETIC","SEIZED","UPLOAD","OSINT_SURFACE","CHAIN"]`, `tor_enabled=false`, `person_lookup_enabled=false`, `telegram_enabled=false`, `max_requests_per_hour={"surface":60,"dark":12,"chain":120,"identity":20,"telegram":30}`, `retention_days=null`.
- Lifecycle: OPEN → CLOSED (threads read-only, monitoring paused) → OPEN (reopen) ; CLOSED → ARCHIVED (owner only; read-only forever). Every transition audited with reason.
- Members: add/update/remove; invariants: at least one OWNER; a user cannot remove their own OWNER role if they are the last; ADMIN may act on any case.
- Timeline: UNION of evidence ingests, extraction runs, analytic runs, decisions, alerts, reports, membership changes, status changes → `{at, kind, title, ref{type,id}}` ordered by `at desc, id`.
- Summary: counts of evidence by source class and status, observations by type, pending candidates, open alerts, active watchlist items, threads, last activity.

### Audit

- `record()` writes within the caller's transaction (business mutation and audit commit together).
- Middleware: for every non-GET request that returns < 500, record `http.<route_name>` with status, actor, case id (from path params), request id. Tool calls, captures and decisions add their own richer events in later plans.
- `GET /cases/{id}/audit?cursor&limit&action&actor` (AUDIT_VIEW_CASE); `GET /audit` (AUDIT_VIEW_GLOBAL).
- `result_hash`: SHA-256 of the canonical JSON of the response body for exports and decisions.

---

## Tasks

- [ ] **T1 passwords, jwt, cookies**: unit tests for hash/verify, expiry, tampered token, cookie attributes per environment.
- [ ] **T2 sessions + login/refresh/logout/change-password**: integration tests for the happy path, wrong password (generic message), lockout after 5 (time-frozen), reuse detection revoking all sessions, forced password change gating.
- [ ] **T3 bootstrap-admin CLI**: refuses second run; password never printed.
- [ ] **T4 service tokens**: create/list/revoke; scopes enforced on a stub route; expiry.
- [ ] **T5 authz**: matrix as data; `require`/`require_case`; tests for every role × a representative permission; VIEWER cannot DECIDE (scenario 35); ADMIN sees all.
- [ ] **T6 field encryption**: round trip, AAD mismatch fails, blind index stable and normalised (trim, lowercase for handles).
- [ ] **T7 cases**: codes, create/list/get/patch, policy validation (unknown source class rejected; caps ≥ 0), close/reopen/archive with invariants, anti-enumeration (unknown UUID and foreign case both 404 with identical bodies).
- [ ] **T8 members**: invariants and audit.
- [ ] **T9 timeline + summary**: SQL union with stable ordering; test with fixtures.
- [ ] **T10 audit middleware + trigger**: middleware records; trigger blocks update/delete; list endpoints with filters.

## Acceptance gate

`tests/integration/test_auth_flow.py` covers login → me → refresh → mutation with CSRF → logout; `test_anti_enumeration.py` passes; a VIEWER gets 403 `FORBIDDEN` on `POST /decisions` (stub) and the event appears in the case audit list.

## Handoff

Plan 02 uses `require_case(EVIDENCE_UPLOAD)` and `audit.record` and `crypto.fields.encrypt` for locators.
