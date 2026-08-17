# DARKNETRA Optional Lawful Public-Source Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strictly policy-gated, read-only collector that can capture authorized publicly observable HTTP `.onion` content into the existing Evidence Vault without authentication, interaction, purchases, access-control bypass, or dependence by the core product/demo.

**Architecture:** The collector is an isolated service with the only optional egress/Tor network membership. Investigators/admins register encrypted source locators and written authority references through a source registry; jobs are policy-validated before execution. The collector permits only GET/HEAD, no cookies/credentials/JavaScript/forms, bounded depth/bytes/rate, no clearweb redirects, and writes WARC-like capture artifacts through the same ingestion boundary. The API/worker/LLM services do not receive general Tor egress.

**Tech Stack:** Python 3.12, requests/httpx-compatible client with SOCKS support, Tor daemon container/service, Celery, PostgreSQL source registry, WARC writer, FastAPI, React/TanStack Query, pytest with injected fake transport/local test server.

## Global Constraints

- This plan is optional. Start only after Plans 01-07 are stable and the team has explicit approval to include a public-source collector.
- The core system and finale demo MUST continue to function when collector profile is disabled.
- The collector MUST NOT create/log into market accounts, submit forms, send messages, accept invitations, solve CAPTCHAs, bypass bot/access controls, defeat encryption, exploit services, contact sellers, or purchase/facilitate controlled substances.
- Allowed methods: `GET`, `HEAD` only.
- Allowed schemes: `http` for `.onion` hidden services; no automatic clearweb pivot.
- Follow clearweb redirects: false.
- Execute JavaScript: false.
- Accept/set cookies: false; discard `Set-Cookie`.
- Send Authorization headers/client certificates: false.
- Max crawl depth default 1; max 25 pages/job; max 10 MiB/page; max 50 MiB/job; default 6 requests/minute/source; explicit global concurrency bound.
- Allowed response content types: `text/html`, `application/xhtml+xml`, `text/plain`; other content is metadata-only/quarantined according to policy rather than automatically downloaded.
- Block obvious executable/archive extensions/content types by default.
- No operational onion locators are committed in source code, fixtures, screenshots, docs, logs, or demo recordings.
- Full locators and authority references are encrypted at application level; UI redacts them by default and reveal is audited.
- Collector never takes commands from page content or an LLM.

---

## Policy baseline

```yaml
schema_version: 1
enabled: false
allowed_schemes: [http]
allowed_host_suffixes: [.onion]
allowed_methods: [GET, HEAD]
follow_clearweb_redirects: false
execute_javascript: false
accept_cookies: false
max_depth: 1
max_pages_per_job: 25
max_bytes_per_page: 10485760
max_bytes_per_job: 52428800
requests_per_minute: 6
allowed_content_types:
  - text/html
  - text/plain
  - application/xhtml+xml
blocked_extensions:
  - .exe
  - .dll
  - .msi
  - .apk
  - .scr
  - .jar
  - .iso
store_warc: true
store_screenshot: false
redact_source_locator_in_ui: true
```

---

### Task 1: Add encrypted Source Registry schema and policy model

**Files:**
- Create source registry models/schemas/migration/service/tests.
- Extend application encryption utility if created in prior plans; otherwise implement AES-256-GCM envelope abstraction with environment-provided master key version.

**Interfaces:**
- Source fields: stable ID, case/global scope according to policy, encrypted locator, locator equality hash, description, parser/profile, approval state, encrypted authority reference, health, last success/failure, mirror group, parser version, enabled state.

- [ ] **Step 1: Write tests** ensuring plaintext locator/authority is absent from DB serialized row/log representation and equality hash cannot reconstruct locator.
- [ ] **Step 2: Implement encryption envelope** using maintained cryptographic library AES-256-GCM, random nonce, key version, authenticated associated data containing resource/type ID; no custom crypto.
- [ ] **Step 3: Validate locator syntax** after decryption at service boundary: host must be `.onion`, no userinfo credentials, no fragment needed for request, method profile read-only.
- [ ] **Step 4: Require non-empty written authority reference and ADMIN/authorized role for enablement.
- [ ] **Step 5: Audit create/update/enable/disable/reveal actions.
- [ ] **Step 6: Commit** `feat: add encrypted authorized source registry`.

---

### Task 2: Implement collector policy engine independent of HTTP client

**Files:**
- Create `services/collector/darknetra_collector/policy.py` and tests.

**Interfaces:**
- `CollectorPolicy.validate_job(job) -> ValidatedJob`.
- `validate_request(url, method, depth, bytes_so_far, pages_so_far) -> PolicyDecision`.

- [ ] **Step 1: Write exhaustive negative tests** clearweb host, HTTPS if disallowed policy, IP literal, localhost, credentials in URL, method POST/PUT/DELETE/PATCH, depth >1, page/job limits, executable extension, malformed onion hostname.
- [ ] **Step 2: Write redirect policy tests** onion->clearweb denied; onion->different onion allowed only if registry/policy explicitly permits target source/mirror; redirect loop bounded.
- [ ] **Step 3: Implement pure policy functions** with no network calls so unit tests cannot accidentally reach internet.
- [ ] **Step 4: Commit** `feat: enforce read only collector policy`.

---

### Task 3: Implement HTTP transport with Tor-only egress and no session state

**Files:**
- Create collector transport/client tests.
- Modify Compose with profile `collector` and separate networks.

**Interfaces:**
- `fetch(request: ValidatedRequest) -> CapturedResponse`.

- [ ] **Step 1: Inject transport in tests**; default tests use local/fake response and never Tor/live `.onion`.
- [ ] **Step 2: Implement SOCKS proxy configuration from environment**; DNS resolution through proxy (`socks5h` semantics) rather than local resolver.
- [ ] **Step 3: Create fresh/request-bounded client state** that never persists cookies; explicitly ignore `Set-Cookie`; fixed benign investigator user-agent identifying tool where policy permits.
- [ ] **Step 4: Do not send Referer across distinct sources and never send Authorization/Cookie headers.
- [ ] **Step 5: Stream response with byte ceiling**; stop/mark truncated before exceeding page/job limit.
- [ ] **Step 6: Compose network design**: `collector` joins internal app/control network plus `tor-egress`; API/analysis workers do not join tor-egress. Tor service exposes SOCKS only to collector network, not host in base profile.
- [ ] **Step 7: Commit** `feat: isolate collector through Tor egress profile`.

---

### Task 4: Implement safe discovery/parser adapters without interaction

**Files:**
- Create collector parser/link-discovery modules/tests.

**Interfaces:**
- Extract links from HTML `<a href>` only; no forms/buttons/scripts; normalize/dedupe and submit each candidate to policy before follow.

- [ ] **Step 1: Tests** links relative/absolute, javascript/data/mailto, form actions, hidden inputs, meta refresh, base tag, clearweb links, malformed URLs.
- [ ] **Step 2: Ignore forms entirely** and never infer form submission from page text.
- [ ] **Step 3: Do not execute JavaScript or use browser automation**.
- [ ] **Step 4: Depth-1 discovery only** from registered seed/approved mirror group; enforce max pages and rate limit before queueing.
- [ ] **Step 5: Page content cannot change policy/config** even if it contains instruction-like text.
- [ ] **Step 6: Commit** `feat: add bounded passive onion discovery`.

---

### Task 5: Capture requests/responses into Evidence Vault-compatible WARC package

**Files:**
- Create capture writer/integration adapter/tests.

**Interfaces:**
- Collector returns capture file + manifest to authenticated API ingestion endpoint or trusted internal service interface; it does not directly mutate evidence database.

- [ ] **Step 1: Write capture tests** request URL protected/redacted in normal logs, response headers/body captured within policy, timestamp/tool version/source ID present.
- [ ] **Step 2: Write WARC using standards-compatible library** and compute local SHA-256 before transfer.
- [ ] **Step 3: Internal ingestion verifies hash again** and creates `PUBLIC_OBSERVATION` evidence referencing source registry/authority.
- [ ] **Step 4: Truncated responses record truncation reason/byte counts and are not silently treated complete.
- [ ] **Step 5: Commit** `feat: preserve passive collector captures through evidence vault`.

---

### Task 6: Implement collection job scheduling, rate/concurrency limits, and failure states

**Files:**
- Create collector jobs/service/API tests.

**Interfaces:**
- Job status appears in authoritative Plan 03 jobs table; failure codes include `TOR_UNAVAILABLE`, `SOURCE_UNREACHABLE`, `POLICY_BLOCKED`, `CONTENT_TYPE_BLOCKED`, `BYTE_LIMIT`, `TIMEOUT`, `REDIRECT_BLOCKED`.

- [ ] **Step 1: Write concurrency/rate tests** with fake clock/transport; one source cannot exceed configured requests/minute and global worker concurrency.
- [ ] **Step 2: Implement retries only for transient transport errors** with bounded exponential backoff; policy blocks are non-retryable.
- [ ] **Step 3: Source health updates last success/failure/failure reason without disabling automatically after one error.
- [ ] **Step 4: Collection never becomes infinite monitor by default; explicit scheduled-monitor feature has minimum hourly cadence and authorization/audit if implemented.
- [ ] **Step 5: Commit** `feat: add bounded collector job orchestration`.

---

### Task 7: Add Source Registry/collector administration UI

**Files:**
- Replace `/intelligence/sources` shell with source registry feature.
- Create tests/E2E.

- [ ] **Step 1: Tests** redacted locator display, authority present indicator, enabled/disabled state, health/failure text, audited reveal confirmation.
- [ ] **Step 2: Create/edit form** validates `.onion` source and displays immutable safety policy summary; no credential fields, no POST configuration, no JavaScript toggle.
- [ ] **Step 3: Enable action requires confirmation referencing written authorization; disable is immediate/audited.
- [ ] **Step 4: Manual collection action** shows GET/HEAD-only bounded policy and creates job; does not open source in browser.
- [ ] **Step 5: Health panel** distinguishes Tor unavailable, source unavailable, policy block, parser failure.
- [ ] **Step 6: Commit** `feat: add authorized source registry UI`.

---

### Task 8: Add collector security regression tests

**Files:**
- Create security tests.

- [ ] **Step 1: SSRF** block localhost, RFC1918/IP literal/clearweb and URL userinfo tricks even if supplied after redirect.
- [ ] **Step 2: DNS/redirect confusion** decisions based on validated URL/host policy; collector has no direct clearweb network path in Compose.
- [ ] **Step 3: Cookie/auth** fake server sets cookie then second request asserts it is not sent.
- [ ] **Step 4: Method** fake page with forms cannot cause POST.
- [ ] **Step 5: Active content** scripts/meta refresh/forms ignored; page text containing `ignore policy` cannot alter settings.
- [ ] **Step 6: Executable/content-type** blocked response is not stored as normal safe body; metadata/failure recorded according to policy.
- [ ] **Step 7: Log redaction** capture logs never contain full configured source locator when redaction enabled.
- [ ] **Step 8: Commit** `test: harden lawful collector boundaries`.

---

### Task 9: Optional supervised real-world validation protocol

**Files:**
- Create `docs/operations/authorized-public-observation.md`.
- No live locators in repository.

- [ ] **Step 1: Document prerequisites** written organizer/agency authorization, designated supervisor, approved source list loaded at runtime, no accounts/logins/contact/purchase, collection window, evidence handling destination.
- [ ] **Step 2: Document minimal validation** one approved public source/search result page -> passive GET -> WARC/evidence hash -> extraction -> candidate review. Success is proving pipeline can process genuine public observation, not proving market-wide coverage.
- [ ] **Step 3: Document stop conditions** unexpected login/CAPTCHA/access gate, illegal content requiring special handling, request to interact, source outside allowlist, redirect outside onion policy, uncertainty about authorization.
- [ ] **Step 4: Document finale rule** live validation results are optional supplementary evidence; synthetic replay remains primary reliable demo.
- [ ] **Step 5: Commit** `docs: define supervised public observation protocol`.

---

### Task 10: Final optional-collector verification

**Files:**
- Create `docs/verification/plan-08-optional-lawful-collector.md`.

- [ ] **Step 1: Run complete collector unit/security suite with fake/local transports**.
- [ ] **Step 2: Run Compose profile disabled and prove core product still passes smoke.
- [ ] **Step 3: Run collector profile against test transport/Tor connectivity test endpoint where lawful, not a criminal service.
- [ ] **Step 4: Verify API/worker containers do not join Tor-egress network.
- [ ] **Step 5: Verify no operational source strings** with repository secret/content scan.
- [ ] **Step 6: Record whether supervised real-world validation was performed; if not, state `not performed` rather than implying success.
- [ ] **Step 7: Commit** `docs: verify optional collector safety boundary`.

---

## Plan 08 Definition of Done

- Collector is disabled by default and separated behind Compose profile/policy gate.
- Full source locator/authority is encrypted/redacted and never committed.
- Only GET/HEAD are possible; no form submission/auth/cookies/JavaScript/browser interaction.
- Clearweb/localhost/IP-literal/credential/redirect SSRF paths are blocked by tests and network isolation.
- Depth/page/byte/rate/concurrency limits are enforced before requests/body growth.
- Captures enter existing Evidence Vault with independent hash verification and provenance.
- Failures are explicit policy/transport states.
- Core product remains fully operational with collector disabled.
- Any genuine public observation occurs only under written supervised authorization and is not required for the competition demo.