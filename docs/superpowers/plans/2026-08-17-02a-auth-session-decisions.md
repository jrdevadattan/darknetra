# DARKNETRA Authentication Session Decisions — Normative Supplement to Plan 02

> **For agentic workers:** This file is a normative companion to `2026-08-17-02-api-auth-cases.md`. Where Plan 02 leaves a library/mechanism choice open, this file fixes the choice. Do not substitute another scheme without an approved ADR.

## Fixed choices

### JWT library and signing

Use:

```toml
"pyjwt[crypto]>=2.10,<3"
```

Access JWT algorithm: `HS256` with a runtime-only 32-byte random signing key loaded from `DARKNETRA_JWT_SIGNING_KEY_B64` and validated to decode to exactly 32 bytes. Do not commit the key. Claims:

```text
sub = stable user UUID string
sid = auth session UUID string
typ = access
iss = darknetra
aud = darknetra-web
iat, nbf, exp
jti = random UUID/token ID
```

Do not embed permissions, case memberships, display names, evidence values, or secrets in JWT claims. Authorization always reads current database state.

Access lifetime: 15 minutes.

### Refresh token

Refresh token is opaque, not JWT:

```python
secrets.token_urlsafe(48)
```

Store only `SHA-256(UTF8(refresh_token))` because the token is server-generated high-entropy random material. Compare using constant-time `hmac.compare_digest` on fixed-length decoded digest bytes/hex strings.

Refresh lifetime: 8 hours.

Successful refresh atomically:

```text
validate current session/token
-> revoke/replace current refresh digest
-> generate new opaque refresh token
-> generate new CSRF token
-> update session expiry/last_seen
-> issue new access JWT
-> set new cookies
-> append audit event
-> one database commit
```

Old refresh token must fail after rotation. Reuse of a previously rotated token revokes the session and emits `REFRESH_TOKEN_REUSE_DETECTED`.

### Cookie names and attributes

```text
darknetra_access
  HttpOnly=true
  SameSite=Strict
  Secure=true outside explicit local-development HTTP mode
  Path=/
  Max-Age <= 900

darknetra_refresh
  HttpOnly=true
  SameSite=Strict
  Secure=true outside explicit local-development HTTP mode
  Path=/api/v1/auth
  Max-Age <= 28800

darknetra_csrf
  HttpOnly=false
  SameSite=Strict
  Secure=true outside explicit local-development HTTP mode
  Path=/
  Max-Age <= current auth session expiry
```

Never put any token in localStorage/sessionStorage/IndexedDB application state.

### CSRF mechanism

Use a server-session-bound synchronizer token:

1. Generate `csrf_token = secrets.token_urlsafe(32)` on login and every refresh.
2. Store `SHA-256(csrf_token)` on the `auth_sessions` row.
3. Set plaintext CSRF token only in the non-HttpOnly `darknetra_csrf` cookie.
4. Frontend mutation client reads that cookie and sends `X-CSRF-Token: <value>`.
5. Backend state-changing cookie-authenticated endpoint requires header and compares its SHA-256 to session `csrf_token_hash` using constant-time comparison.
6. Safe methods GET/HEAD/OPTIONS do not require CSRF header but remain authorized normally.
7. Login is protected by strict Origin/Host validation and login throttling; change-password/refresh/logout require the session CSRF check where a valid session cookie is present.

This is not a stateless double-submit scheme: the CSRF value is bound to authoritative server session state.

### Auth session table minimum fields

```text
id
user_id
refresh_token_hash
csrf_token_hash
created_at
expires_at
last_seen_at
revoked_at nullable
revocation_reason nullable
user_agent_hash nullable
remote_context_hash nullable
```

Do not store raw user-agent/IP unless an explicit privacy/operational decision requires it; hashed/coarsened context is optional and is not used as authentication proof.

### Password policy

Use Argon2id via `argon2-cffi`. Minimum password policy for hackathon deployment:

```text
length >= 12
length <= 128
not equal to username case-insensitively
no forced composition rule
```

Do not silently trim password characters. Reject NUL. Password change requires current password unless user is in forced bootstrap-change state with an already authenticated session.

### Login throttling

Per user normalized username plus service-level coarse limiter:

```text
5 consecutive failed password attempts for an existing active user -> locked_until = now + 5 minutes
successful login -> failed_login_count = 0, locked_until = null
unknown username -> perform dummy Argon2 verification against process-held dummy hash before generic failure response
all client failures -> same generic 401 body
```

Rate limiting must not reveal whether username exists.

### CORS/origin policy

Production same-origin deployment is preferred. Development API allows only configured exact origin `http://localhost:3000` with credentials. Never use `Access-Control-Allow-Origin: *` with credentials.

Mutation requests additionally validate `Origin` against configured allowlist when browser Origin header is present.

### Frontend API behavior

`apiFetch` uses `credentials: "include"`. It never reads access/refresh cookies. For non-GET/HEAD/OPTIONS methods it reads the named CSRF cookie and adds `X-CSRF-Token`.

On 401 from normal API request, do not blindly replay mutations. Query/session layer may perform one refresh attempt, then re-fetch idempotent reads. A failed mutation is surfaced for user retry rather than automatically replayed unless endpoint/idempotency contract explicitly allows it.

### Audit event names

Use stable strings:

```text
LOGIN_SUCCEEDED
LOGIN_FAILED
ACCOUNT_TEMP_LOCKED
SESSION_REFRESHED
REFRESH_TOKEN_REUSE_DETECTED
LOGOUT
PASSWORD_CHANGED
ADMIN_BOOTSTRAPPED
```

Audit metadata never includes passwords, JWTs, refresh tokens, CSRF tokens, token hashes, or signing keys.

## Required tests added to Plan 02 execution

Plan 02 is not complete unless tests prove:

- access cookie is HttpOnly/SameSite Strict and max age <=15m;
- refresh cookie is HttpOnly/SameSite Strict, scoped to auth path and <=8h;
- CSRF cookie is not HttpOnly and mutation header must hash-match session;
- missing/wrong CSRF fails a valid authenticated mutation;
- old refresh token fails after successful rotation;
- reuse of rotated refresh token revokes session;
- session revocation invalidates refresh and current-user authorization according to access-token/session lookup policy;
- no access/refresh token is written to Web Storage;
- CORS credentials origin is exact configured origin, never wildcard;
- unknown user and wrong password return identical status/body shape;
- five failures lock temporarily and a successful login after expiry resets counters;
- bootstrap `must_change_password` gate works.

## Implementation dependency additions

When Plan 02 reaches auth tasks, add exact dependency families:

```toml
"argon2-cffi>=25,<26"
"pyjwt[crypto]>=2.10,<3"
```

Keep patch versions locked by `uv.lock`.
