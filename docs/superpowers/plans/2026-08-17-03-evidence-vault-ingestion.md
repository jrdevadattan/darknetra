# DARKNETRA Evidence Vault and Safe Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a tamper-evident, case-scoped Evidence Vault that preserves immutable originals, records provenance/custody, creates safe derivatives, and ingests approved WARC, HTML, TXT, JSON, CSV, ZIP chat exports, images, and text-bearing PDFs without executing active content.

**Architecture:** PostgreSQL stores authoritative evidence metadata, manifests, custody events, lineage, processing jobs, and quarantine states. Original bytes are written to a content-addressed object-store abstraction whose default implementation is a local filesystem mounted into the API/worker containers; derived content is always a separate object linked to its parent. Ingestion performs policy checks before parsing, queues safe derivative work, and never mutates an original artifact.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, local content-addressed filesystem, Python `hashlib`, `python-magic`/libmagic-compatible MIME detection, `warcio`, `selectolax` with BeautifulSoup fallback, `nh3` for sanitization, Pillow, `pypdf` for text-bearing PDFs, standard-library `zipfile` with explicit anti-bomb/path-traversal rules, pytest/Hypothesis, Celery/Redis introduced in this plan for background ingestion jobs.

## Global Constraints

- Begin only after Plans 01, 02, and 03a verification pass. Reproduce the Plan 03a tested-tree identity recorded in `docs/verification/plan-03a-sensitive-field-encryption.md` before creating Plan 03 persistence.
- Original evidence bytes are immutable after successful ingestion.
- Every derivative references its parent evidence ID and transformation method/version.
- Compute SHA-256 for every original and derivative; SHA-512 is optional but supported by manifest model.
- Hash mismatch never causes the stored expected digest to be silently updated.
- Preserve byte length, UTC capture/ingest timestamps, original timezone/context when supplied, source class, source type, acquisition method, collector identity, tool/version, case ID, notes/errors, and custody history.
- Approved source classes for the MVP: `SYNTHETIC`, `RESEARCH_ARCHIVE`, `AUTHORIZED_IMPORT`, `PUBLIC_OBSERVATION`. `PUBLIC_OBSERVATION` creation requires the policy/reference fields defined here and does not imply unrestricted live collection.
- Supported input types in this plan: WARC/WARC.GZ, HTML/XHTML, UTF-8/recognized text, JSON, CSV, ZIP chat export, PNG/JPEG/WebP, text-bearing PDF.
- Do not execute JavaScript, macros, binaries, downloaded scripts, document actions, media players, or embedded executables.
- Archive extraction must prevent path traversal, symlink escape, archive bombs, excessive file counts, nested-archive recursion, and special-device entries.
- Browser never receives unrestricted filesystem paths or object-store credentials.
- API authorization reuses Plan 02 case-scoped policy.
- Evidence mutations and audit events are committed transactionally where metadata is involved; byte writes use staging + verified atomic promotion.
- API and worker startup construct and validate `Settings.require_sensitive_field_crypto()`. Startup and readiness fail closed when the required keyring, active version, or blind-index key is absent or invalid.
- Do not implement OCR in this plan; image-only PDFs are marked `TEXT_NOT_AVAILABLE` rather than misrepresented as parsed.

---

## Evidence states

```text
STAGING
PRESERVED
QUARANTINED
PROCESSING
READY
PARTIAL
FAILED
INTEGRITY_MISMATCH
```

`PRESERVED` means original bytes and manifest are durably stored and hash-verified. `READY` means approved derivatives/parsers completed. Parsing failure may yield `PARTIAL` while the original remains preserved.

---

### Task 1: Add Redis/Celery processing boundary and job schema

**Files:**
- Modify: `docker-compose.yml`, `docker-compose.dev.yml`, `.env.example`, `apps/api/pyproject.toml`.
- Create: `apps/api/darknetra_api/jobs/celery_app.py`
- Create: `apps/api/darknetra_api/models/job.py`
- Create Alembic revision.
- Create: `apps/api/tests/integration/test_jobs.py`

**Interfaces:**
- Redis service name `redis`; Celery queue `ingest`.
- Authoritative `jobs` row records `PENDING|RUNNING|SUCCEEDED|FAILED|RETRYING` with case/resource references; Redis is transient only.

- [ ] **Step 1: Write failing job-state persistence test** verifying a queued job row survives Redis flush because state is stored in PostgreSQL.
- [ ] **Step 2: Add Redis/Celery dependencies and Compose services** with health checks, no host port in base Compose, worker command pinned to `darknetra_api.jobs.celery_app:celery_app`, and runtime-only sensitive-field crypto variables supplied to API and worker without static synthetic/test keys.
- [ ] **Step 3: Implement job model and migration** with unique idempotency key, attempt count, error code/message, created/started/finished timestamps.
- [ ] **Step 4: Implement Celery app with JSON-only serializer**; disable pickle; set bounded task time limits and explicit retry policy.
- [ ] **Step 5: Construct sensitive-field crypto during API and worker startup** and include the result in readiness. Add tests that both processes start with a valid runtime keyring and fail closed on a missing key source, missing blind-index key, invalid version, duplicate key material, or unconfigured active version.
- [ ] **Step 6: Run Postgres/Redis/worker integration test** and prove Redis restart does not delete authoritative job history.
- [ ] **Step 7: Commit** with `feat: add durable analysis job boundary`.

---

### Task 2: Implement evidence metadata, lineage, custody, and manifest schema

**Files:**
- Create: `apps/api/darknetra_api/models/evidence.py`
- Create: `apps/api/darknetra_api/models/custody.py`
- Create: `apps/api/darknetra_api/schemas/evidence.py`
- Create Alembic revision.
- Create integration tests.

**Interfaces:**
- Tables: `evidence_artifacts`, `evidence_sensitive_values`, `evidence_derivations`, `custody_events`.
- `EvidenceArtifact` contains immutable expected digest fields after preservation.
- `EvidenceSensitiveValue` is case and evidence scoped. It identifies one of `SOURCE_LOCATOR`, `AUTHORITY_REFERENCE`, `PROTECTED_NOTE`, `CUSTODY_NOTE`, `CONTACT`, or `POLICY_RESTRICTED_WALLET` and stores `key_version`, `nonce_b64`, `ciphertext_b64`, and a nullable `blind_index`. The source-locator deduplication workflow stores an index; other kinds store one only when a canonical equality/deduplication workflow is documented. Contacts may also store a non-sensitive contact kind. Policy-restricted wallets may also store non-sensitive network/asset metadata. It never stores plaintext or a ciphertext-only shortcut.

- [ ] **Step 1: Write schema and service tests** for unique evidence ID, case foreign key, valid source class/state, immutable digest service behavior, parent-child lineage, append-only custody rows, and all six protected value kinds. For each protected kind, the test must prove the owning write path uses the public `compose_sensitive_field_purpose(resource_type, field_name)`, calls `SensitiveFieldCrypto.encrypt`, and persists all three fields returned by `pack_envelope`. Prove source-locator deduplication stores a purpose-specific HMAC blind index, while kinds without a documented equality workflow store null. A column named `ciphertext`, a partial envelope, raw SHA-256, a hard-coded parallel purpose, or a test-only helper path does not satisfy the test.
- [ ] **Step 2: Implement non-sensitive artifact fields**: `id`, `case_id`, `source_class`, `source_type`, `acquisition_method`, `collector_user_id`, `captured_at`, `ingested_at`, `original_timezone`, `media_type`, `size_bytes`, `sha256`, `sha512`, `object_key`, `state`, `quarantine_reason`, `tool_name`, `tool_version`, policy flags, and timestamps. Do not add `source_locator_ciphertext`, `authority_reference_ciphertext`, `notes_ciphertext`, or any other ciphertext-only scalar.
- [ ] **Step 3: Implement protected-value persistence** through the Plan 03a boundary. The repository accepts `pack_envelope` output plus an optional HMAC blind index, validates every load with `unpack_envelope`, and omits plaintext, envelope internals, and blind indexes from ORM repr and ordinary schemas. Source locators, authority references, protected analyst notes/rationales, custody notes, contacts, and policy-restricted wallets all use this path.
- [ ] **Step 4: Implement the owning reveal adapters and tests**. Add the public `compose_sensitive_field_purpose(resource_type, field_name)` helper and use it in both writers and reveal adapters. Bind the case-scoped provider, field-specific policy, crypto service, and request ID once to the request session, keep provider and policy adapters read-only, and call the exact seven-argument `reveal_sensitive_value`. Tests must cover write → pack → persist/load → unpack → reveal without a hard-coded purpose, permitted audited reveal, viewer denial, cross-case not-found equivalence, `Cache-Control: no-store` at the HTTP boundary, and failure to return plaintext when the audit commit fails. Extend the Plan 03a rotation-result repr regression to assert the rotated envelope nonce, ciphertext, and plaintext are absent.
- [ ] **Step 5: Implement derivation rows** with `parent_evidence_id`, `child_evidence_id`, `transformation`, `transformer_version`, parameters JSON, timestamp.
- [ ] **Step 6: Generate/apply migration** and run downgrade/upgrade on disposable DB. Inspect the migration to confirm every protected row has the complete envelope, a nullable blind-index column, and no plaintext or ciphertext-only legacy columns.
- [ ] **Step 7: Commit** `feat: define evidence provenance schema`.

---

### Task 3: Implement content-addressed local object store with staging and atomic promotion

**Files:**
- Create: `apps/api/darknetra_api/storage/base.py`
- Create: `apps/api/darknetra_api/storage/local.py`
- Create: `apps/api/tests/unit/test_local_object_store.py`
- Modify Compose volumes/environment.

**Interfaces:**
- `ObjectStore.put_verified(stream, expected_sha256=None) -> StoredObject`
- `ObjectStore.open(object_key) -> BinaryIO`
- `ObjectStore.verify(object_key, expected_sha256) -> bool`
- Key layout: `sha256/<first2>/<next2>/<fullhex>`; no original filename in storage path.

- [ ] **Step 1: Write tests** for deterministic key, duplicate content deduplication, partial-write cleanup, expected-hash mismatch, atomic promotion, read-only final file mode where platform supports it.
- [ ] **Step 2: Implement streaming hash/write** to a random staging filename under same filesystem; fsync file, verify digest, atomically `os.replace` into content path; never trust caller filename for paths.
- [ ] **Step 3: Implement open/verify** and reject keys not matching generated content-key grammar.
- [ ] **Step 4: Add named Compose volume `evidence_store`** mounted only into API/worker services that need it; web gets no mount.
- [ ] **Step 5: Run Hypothesis test** generating arbitrary byte strings and verifying round-trip digest/object key.
- [ ] **Step 6: Commit** `feat: add content addressed evidence storage`.

---

### Task 4: Implement upload staging, size/MIME policy, and preservation transaction

**Files:**
- Create: `apps/api/darknetra_api/policy/ingestion.py`
- Create: `apps/api/darknetra_api/services/evidence_ingest.py`
- Create: `apps/api/darknetra_api/routes/evidence.py`
- Create tests.

**Interfaces:**
- `POST /api/v1/cases/{case_id}/evidence` multipart upload plus JSON metadata.
- Default single-artifact max upload: 100 MiB in MVP; configurable downward/upward by admin policy, hard ceiling 500 MiB in this plan.

- [ ] **Step 1: Write negative tests** for unauthorized case, missing metadata, oversize Content-Length, streamed body exceeding declared/max size, MIME mismatch, empty file, unsupported type.
- [ ] **Step 2: Implement source metadata schema** requiring source class/type/acquisition method; `PUBLIC_OBSERVATION` and `AUTHORIZED_IMPORT` require non-empty authority reference input. Pass source locators, authority references, and protected notes to the Task 2 protected-value write service so complete envelopes are persisted; create a blind index only for the documented source-locator deduplication workflow.
- [ ] **Step 3: Implement MIME detection from bytes**; filename extension is advisory only. Supported MIME allowlist maps to parser family.
- [ ] **Step 4: Stream upload directly to object-store staging** without reading entire artifact into memory.
- [ ] **Step 5: Persist evidence row only after verified object promotion**; if DB commit fails, retained unreferenced object is safe and later garbage-collection tooling may reconcile; do not delete a content-addressed object that might be shared by another evidence row.
- [ ] **Step 6: Append audit and custody events** `EVIDENCE_INGESTED` and `CUSTODY_CREATED` in same DB transaction as artifact metadata.
- [ ] **Step 7: Queue derivative processing after commit** using job idempotency key `ingest:{evidence_id}:{pipeline_version}`.
- [ ] **Step 8: Commit** `feat: preserve uploaded evidence safely`.

---

### Task 5: Implement secure ZIP/chat-export extraction

**Files:**
- Create: `apps/api/darknetra_api/parsers/archive.py`
- Create: `apps/api/darknetra_api/parsers/chat_export.py`
- Create adversarial fixtures programmatically in tests; do not commit real chat exports.

**Interfaces:**
- Archive policy defaults: max 2,000 members; max expanded bytes 250 MiB; max compression ratio 100:1 per entry; max nesting depth 1; symlinks/devices rejected.

- [ ] **Step 1: Write tests constructing ZIPs in memory** for `../escape`, absolute paths, duplicate normalized names, symlink metadata, huge declared size, high compression ratio, nested archive, excessive members, benign JSON/HTML/TXT/media bundle.
- [ ] **Step 2: Implement safe member-name normalization** with POSIX semantics independent of host OS; reject names escaping synthetic extraction root.
- [ ] **Step 3: Never extract untrusted ZIP directly to a persistent shared directory**; stream approved members into child evidence objects through ObjectStore.
- [ ] **Step 4: Create child evidence/derivation rows** for each retained member with parent ZIP lineage and original archive path stored as metadata, not filesystem path.
- [ ] **Step 5: Implement generic chat-export adapter** that recognizes JSON/HTML/TXT conversation records only from content structure; it does not claim platform decryption or private-platform access.
- [ ] **Step 6: Commit** `feat: safely ingest archived chat exports`.

---

### Task 6: Implement WARC, HTML, text, JSON, and CSV derivatives

**Files:**
- Create: `apps/api/darknetra_api/parsers/warc.py`
- Create: `apps/api/darknetra_api/parsers/html.py`
- Create: `apps/api/darknetra_api/parsers/text.py`
- Create: `apps/api/darknetra_api/parsers/tabular.py`
- Create parser tests.

**Interfaces:**
- Parser result: `ParsedDerivative(text, metadata, warnings)`; parser never writes DB directly.

- [ ] **Step 1: Write parser tests** for malformed WARC records, gzip corruption, HTML script/style removal, entity decoding, huge DOM limits, invalid UTF-8 replacement reporting, JSON arrays/objects, CSV delimiter/header edge cases, formula-looking cells preserved as text but never executed.
- [ ] **Step 2: Implement WARC response extraction** with `warcio`; record original target URI only in protected metadata and expose redacted locator in UI later.
- [ ] **Step 3: Implement no-network HTML parsing**; strip script/style/noscript/iframe/object/embed active content; derive normalized plain text; sanitize any preview HTML using `nh3` allowlist with links inert/rewritten.
- [ ] **Step 4: Implement text encoding strategy**: UTF-8 first; supported fallback detection may be added only with a deterministic library and warning field; never silently drop undecodable bytes.
- [ ] **Step 5: Implement JSON/CSV parsing with bounded rows/cells**; serialize normalized textual rows for later extraction while retaining original bytes.
- [ ] **Step 6: Commit** `feat: parse text and web evidence derivatives`.

---

### Task 7: Implement image and text-bearing PDF preservation/derivatives

**Files:**
- Create: `apps/api/darknetra_api/parsers/image.py`
- Create: `apps/api/darknetra_api/parsers/pdf.py`
- Create tests.

**Interfaces:**
- Image metadata derivative records dimensions, format, EXIF presence; private EXIF values are not displayed by default.
- PDF result indicates `TEXT_AVAILABLE` or `TEXT_NOT_AVAILABLE`.

- [ ] **Step 1: Write image tests** for decompression-bomb warning, malformed image, huge dimensions, EXIF orientation, valid PNG/JPEG/WebP.
- [ ] **Step 2: Configure Pillow decompression-bomb limit** and convert preview derivative to safe format without carrying active metadata; original remains untouched.
- [ ] **Step 3: Write PDF tests** for normal text page, encrypted PDF with no password, malformed PDF, image-only PDF.
- [ ] **Step 4: Implement PDF text extraction without JavaScript/actions/rendered execution**; encrypted/unreadable document becomes partial/quarantined according to policy, not brute-forced.
- [ ] **Step 5: Mark image-only PDFs `TEXT_NOT_AVAILABLE`**; do not OCR until the stretch plan explicitly enables it.
- [ ] **Step 6: Commit** `feat: derive safe image and PDF representations`.

---

### Task 8: Implement ingestion worker pipeline, idempotency, retry, and partial-state semantics

**Files:**
- Create: `apps/api/darknetra_api/jobs/tasks/ingestion.py`
- Create: `apps/api/darknetra_api/services/derivatives.py`
- Create integration tests using eager Celery mode and real worker smoke test.

**Interfaces:**
- `process_evidence(evidence_id: UUID, pipeline_version: str) -> None` idempotent.

- [ ] **Step 1: Write tests** for duplicate task delivery, parser exception, worker crash after child object created but before metadata commit, retry exhaustion, unsupported parser, and successful re-run after code version change.
- [ ] **Step 2: Implement parser dispatch by trusted detected MIME/parser family**, never filename.
- [ ] **Step 3: Store each normalized text/preview as derivative evidence object** with its own SHA-256 and lineage row.
- [ ] **Step 4: Set final artifact state**: `READY` when required derivatives succeed; `PARTIAL` when safe useful outputs exist with warnings; `FAILED` only when processing failed without invalidating preservation; `QUARANTINED` for policy/security violation.
- [ ] **Step 5: Ensure retries do not duplicate derivation rows** using uniqueness on `(parent, transformation, transformer_version, parameters_digest)`.
- [ ] **Step 6: Commit** `feat: orchestrate idempotent evidence processing`.

---

### Task 9: Implement integrity re-verification and tamper response

**Files:**
- Create: `apps/api/darknetra_api/services/integrity.py`
- Extend evidence routes/schemas.
- Create tests.

**Interfaces:**
- `POST /api/v1/cases/{case_id}/evidence/{evidence_id}/verify`
- Response reports expected/observed digest status without modifying expected digest.

- [ ] **Step 1: Write tamper test**: ingest bytes, verify PASS, alter one byte in test store, verify returns `INTEGRITY_MISMATCH`, expected digest unchanged, audit event appended.
- [ ] **Step 2: Implement re-hash streaming** and audit event `EVIDENCE_INTEGRITY_VERIFIED` or `EVIDENCE_INTEGRITY_MISMATCH`.
- [ ] **Step 3: Prevent normal derivative/analysis pipeline from consuming integrity-mismatched object** until authorized recovery workflow resolves it.
- [ ] **Step 4: Add batch case-integrity summary query** returning counts, not raw full scans in request thread; queue verification for large cases.
- [ ] **Step 5: Commit** `feat: add evidence integrity verification`.

---

### Task 10: Build Evidence UI inventory, detail, lineage, quarantine, and verification flows

**Files:**
- Create: `apps/web/src/features/evidence/types.ts`
- Create API client/query modules.
- Create: evidence table, detail drawer/page, lineage panel, upload dialog, integrity action, restricted preview component.
- Replace Plan 01 `/cases/[caseId]/evidence` shell.
- Create tests/E2E.

**Interfaces:**
- UI never receives server filesystem path/object key as a clickable local path.
- Download/preview uses authorized API endpoints issuing streamed response, not object-store credentials.

- [ ] **Step 1: Write mapper/component tests** for states `PRESERVED/PROCESSING/READY/PARTIAL/QUARANTINED/FAILED/INTEGRITY_MISMATCH` and source-class textual badges.
- [ ] **Step 2: Implement evidence list** with filters source class/type/state/integrity/time and explicit partial/loading/error states.
- [ ] **Step 3: Implement upload dialog** with source metadata, authority-reference conditional requirement, size/type help, no drag-drop auto-submit.
- [ ] **Step 4: Implement restricted preview** blurred by default; reveal requires explicit button and creates server audit event through a reveal endpoint or audited content access endpoint.
- [ ] **Step 5: Implement lineage and manifest view** showing hashes, size, timestamps, tool/version, parent/children, custody timeline; sensitive locator remains redacted.
- [ ] **Step 6: Implement integrity verify action** with confirmation for expensive scan and immutable expected-hash display.
- [ ] **Step 7: E2E** upload a synthetic text artifact, observe processing, open manifest, verify hash; tamper scenario remains backend integration test unless test store exposes fixture hook only in test environment.
- [ ] **Step 8: Commit** `feat: add evidence vault investigator experience`.

---

### Task 11: Add object access authorization, redaction, and download safety headers

**Files:**
- Create/extend evidence content routes.
- Create tests.

**Interfaces:**
- `GET /api/v1/cases/{case_id}/evidence/{id}/content?representation=original|safe-preview`.

- [ ] **Step 1: Write tests** for cross-case denial, VIEWER redaction, restricted-original permissions, `Content-Disposition: attachment` for unsafe originals, `X-Content-Type-Options: nosniff`, restrictive CSP for HTML preview, and no inline rendering of executable/unknown content.
- [ ] **Step 2: Implement streamed content responses** through case authorization; never accept arbitrary object key/path from client.
- [ ] **Step 3: Log/audit original-content access** for restricted artifacts; ordinary metadata list does not count as reveal.
- [ ] **Step 4: Commit** `feat: secure evidence content access`.

---

### Task 12: Add Evidence Vault security/adversarial regression suite

**Files:**
- Create: `apps/api/tests/security/test_ingestion_adversarial.py`
- Create: `apps/api/tests/security/test_archive_bombs.py`
- Create: `apps/api/tests/security/test_html_preview.py`
- Create: `apps/api/tests/security/test_content_access.py`

**Interfaces:** none beyond existing policies.

- [ ] **Step 1: Add path traversal/symlink/archive-ratio/file-count/nested archive cases** generated in memory.
- [ ] **Step 2: Add HTML payloads** with scripts, event handlers, iframe, object/embed, javascript/data URLs, `<base>`, meta refresh; safe preview must contain none of the active behavior.
- [ ] **Step 3: Add MIME spoofing cases** `.jpg` containing ZIP/HTML, `.txt` binary, PDF extension mismatch; detection follows bytes/policy.
- [ ] **Step 4: Add large streaming test** proving upload handler does not call `.read()` without a bounded size; use instrumented stream fixture.
- [ ] **Step 5: Run security tests under worker eager mode and real Compose smoke**.
- [ ] **Step 6: Commit** `test: harden evidence ingestion against adversarial files`.

---

### Task 13: Final Plan 03 verification and documentation

**Files:**
- Create: `docs/architecture/evidence-vault.md`
- Create: `docs/verification/plan-03-evidence-vault-ingestion.md`
- Modify README.

- [ ] **Step 1: Document evidence lifecycle** including original/derivative distinction, object-key grammar, hash semantics, custody, lineage, quarantine, parsers, size/archive limits, access/redaction, worker idempotency.
- [ ] **Step 2: Run fresh verification**:

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
```

- [ ] **Step 3: Run startup/readiness tests and Compose probes** with runtime-generated crypto keys. Prove API and worker readiness succeeds with valid configuration and fails closed for missing or invalid crypto configuration. Scan tracked workflows and Compose files for static Base64 keys, including synthetic/test values.
- [ ] **Step 4: Run explicit forensic integrity experiment** on test store: ingest -> verify pass -> mutate one byte -> verify mismatch -> confirm expected digest unchanged -> restore isolated environment.
- [ ] **Step 5: Record observed results/limits/commit SHA** and commit `docs: verify evidence vault milestone`.

---

## Plan 03 Definition of Done

- Original bytes are content-addressed, hash-verified, immutable through application APIs, and separated from derivatives.
- Evidence metadata, lineage, custody, jobs, and integrity states are authoritative in PostgreSQL.
- ZIP path traversal, symlinks, archive bombs, nested archives, MIME spoofing, active HTML and malformed documents have negative tests.
- WARC/HTML/TXT/JSON/CSV/ZIP/image/text-bearing PDF inputs have safe processing paths.
- Image-only PDF is explicitly not OCRed.
- Parser failures never destroy the preserved original.
- Worker retries are idempotent.
- Browser receives only authorized streamed content, never storage credentials/paths.
- Hash mismatch is detected and never silently rewritten.
- Evidence UI exposes provenance, integrity, lineage, quarantine and explicit restricted reveal.
- Source locators, authority references, protected analyst and custody notes, contacts, and policy-restricted wallets persist complete Plan 03a envelopes under the public shared purpose composer, load through `unpack_envelope`, keep blind indexes nullable and limited to documented equality/deduplication workflows, and reveal only through the audited seven-argument service.
- API and worker startup/readiness validate the Plan 03a crypto configuration and fail closed when it is absent or invalid.
- Full fresh verification is recorded.

## Plan 04 handoff contract

Plan 04 may consume `READY/PARTIAL` normalized text derivatives and safe image derivatives by evidence ID, and may create structured extraction records linked to exact evidence/derivative spans. It must never parse from uncontrolled original bytes when an approved derivative exists. Any extracted contact or policy-restricted wallet value that is persisted must use the Plan 03 protected-value repository, public purpose composer, complete envelope, optional HMAC blind index only for a documented equality/deduplication workflow, `pack_envelope`/`unpack_envelope`, and audited reveal path. Plan 04 must not introduce parallel plaintext, raw-hash, ciphertext-only, decryption, or reveal logic.
