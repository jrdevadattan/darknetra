# DARKNETRA Sensitive-Field Encryption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small, audited application-level envelope-encryption boundary before Evidence Vault metadata begins storing source locators, authority references, analyst/custody notes, contacts, or policy-restricted wallet values.

**Architecture:** Sensitive plaintext is encrypted in the API service using AES-256-GCM with random nonces and a versioned master key supplied only at runtime. PostgreSQL stores ciphertext envelope fields plus keyed equality/deduplication hashes where equality lookup is required; the database never stores the encryption key. Decryption is permission-gated and audited at the service boundary rather than exposed as a generic ORM property.

**Tech Stack:** Python 3.12, `cryptography` AESGCM, HMAC-SHA-256 for blind/equality index, pydantic-settings, SQLAlchemy, pytest/Hypothesis.

## Global Constraints

- Execute after Plan 02 and before Plan 03 evidence ingestion.
- Use established cryptographic libraries only; no custom cipher/mode/KDF.
- Master encryption key and blind-index key are distinct 256-bit secrets provided through runtime environment/secret mount, never committed.
- Key IDs/versions are non-secret and stored with envelopes.
- AES-GCM nonce is random 96-bit and never intentionally reused with the same key.
- Associated authenticated data binds ciphertext to field purpose and resource ID/type so ciphertext cannot be silently moved between fields/resources.
- Equality index uses HMAC-SHA-256 with separate key; never raw SHA-256 of low-entropy sensitive plaintext such as phone/email/source locator.
- Decryption requires explicit caller permission/purpose; full-value reveal creates an audit event.
- Logs/exceptions/repr must not contain plaintext or keys.
- Rotation creates new ciphertext version while preserving audit/history; never silently rewrites historical audit payloads.

---

### Task 1: Add cryptographic settings and typed envelope

**Files:**
- Modify `apps/api/pyproject.toml` and settings.
- Create `apps/api/darknetra_api/security/encryption.py`.
- Create unit tests.

**Interfaces:**

```python
@dataclass(frozen=True)
class EncryptedValue:
    key_version: str
    nonce_b64: str
    ciphertext_b64: str

class SensitiveFieldCrypto:
    def encrypt(self, plaintext: str, *, purpose: str, resource_id: str) -> EncryptedValue: ...
    def decrypt(self, value: EncryptedValue, *, purpose: str, resource_id: str) -> str: ...
    def blind_index(self, plaintext: str, *, purpose: str) -> str: ...
```

- [ ] **Step 1: Write failing round-trip/tamper tests** for UTF-8 values, same plaintext producing different ciphertext, wrong purpose/resource failing authentication, one-byte ciphertext/nonce modification failing, and logs/repr not including plaintext.
- [ ] **Step 2: Add `cryptography` dependency** and explicit settings `DARKNETRA_FIELD_KEY_V1_B64`, `DARKNETRA_FIELD_BLIND_INDEX_KEY_B64`, `DARKNETRA_FIELD_ACTIVE_KEY_VERSION=v1`; validate decoded key length exactly 32 bytes.
- [ ] **Step 3: Implement AESGCM encryption/decryption** with `os.urandom(12)` nonce and AAD bytes `darknetra:{purpose}:{resource_id}:v1`.
- [ ] **Step 4: Implement blind index** `HMAC-SHA256(key, purpose + NUL + normalized_plaintext)`; purpose-specific caller defines normalization before passing value.
- [ ] **Step 5: Run unit/Hypothesis tests** and commit `feat: add sensitive field envelope encryption`.

---

### Task 2: Add reusable encrypted-field persistence helpers without automatic decryption

**Files:**
- Create `apps/api/darknetra_api/security/encrypted_fields.py`.
- Create tests.

**Interfaces:**
- Persist envelope as three explicit columns or JSON object according to owning model; helper converts only explicit service calls.
- ORM models must not expose a property that decrypts on ordinary serialization/repr.

- [ ] **Step 1: Write tests** proving ORM/Pydantic serialization omits ciphertext internals from ordinary API response and never auto-decrypts.
- [ ] **Step 2: Implement helper** `pack_envelope`/`unpack_envelope` validating required fields/key version/base64 lengths.
- [ ] **Step 3: Add redaction helper** for email/phone/wallet/onion/general secret display, operating on plaintext only inside authorized service method then discarding local reference.
- [ ] **Step 4: Commit** `feat: add explicit encrypted field persistence helpers`.

---

### Task 3: Implement audited reveal service

**Files:**
- Create `apps/api/darknetra_api/services/sensitive_values.py`.
- Create integration tests.

**Interfaces:**

```python
async def reveal_sensitive_value(
    *, actor, case_id, resource_type, resource_id, field_name, reason, session
) -> str
```

- [ ] **Step 1: Write authorization tests** VIEWER denied; role/permission configured by owning feature; cross-case inaccessible returns repository-standard 404.
- [ ] **Step 2: Require non-empty reveal reason** bounded 10..500 characters for full-value reveal.
- [ ] **Step 3: Append audit event** containing resource/field/reason, never revealed plaintext.
- [ ] **Step 4: Return plaintext only in response path that requested it**; disable caching with `Cache-Control: no-store` in later HTTP endpoints.
- [ ] **Step 5: Commit** `feat: audit sensitive value reveals`.

---

### Task 4: Add key-version rotation primitives

**Files:**
- Extend encryption service/CLI tests.
- Create `apps/api/darknetra_api/security/keyring.py`.

**Interfaces:**
- Runtime keyring maps version -> 32-byte key; active version selected by setting.
- Rotation command/service always decrypts with old key and encrypts with active key inside authorized offline/admin maintenance context.

- [ ] **Step 1: Test v1 decrypt after v2 becomes active**.
- [ ] **Step 2: Test re-encryption produces v2 envelope and preserves blind index unless blind-index key also intentionally rotates.
- [ ] **Step 3: Unknown key version fails closed with typed error**, not fallback to active key.
- [ ] **Step 4: Document operational rotation and backup requirement**; keys themselves are not backed up into repository archive.
- [ ] **Step 5: Commit** `feat: support versioned sensitive field keys`.

---

### Task 5: Integration gate for Plan 03+

**Files:**
- Create `docs/architecture/sensitive-field-encryption.md`.
- Create `docs/verification/plan-03a-sensitive-field-encryption.md`.

- [ ] **Step 1: Document exact fields required to use this boundary** initially: source locators, authority references, analyst notes/rationales where policy marks sensitive, custody notes, contacts, and policy-restricted wallets.
- [ ] **Step 2: Run fresh `ruff`, pytest, authentication/case regression and Docker API smoke tests** with runtime test keys.
- [ ] **Step 3: Run repository secret scan** and verify no real/base64 test key is in tracked `.env` or docs; tests generate keys at runtime.
- [ ] **Step 4: Record observed verification output/commit SHA** and commit `docs: verify sensitive field encryption`.

---

## Definition of Done

- Sensitive-field AES-256-GCM encryption and separate HMAC blind index are tested.
- AAD binds ciphertext to purpose/resource.
- Key material is runtime-only and versioned.
- Ordinary ORM/API serialization cannot auto-decrypt.
- Full reveal is permission-gated, reasoned and audited without logging plaintext.
- Key rotation can retain old decryption versions and re-encrypt explicitly.
- Plan 03 evidence models use these helpers for source locator/authority/notes rather than merely naming columns `ciphertext`.