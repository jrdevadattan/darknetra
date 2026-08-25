# Sensitive-field encryption boundary

Plan 03 and later features must encrypt sensitive case and evidence metadata in the API before
writing it to PostgreSQL. A column name such as `ciphertext` does not satisfy this contract. The
owning feature must call the tested helpers in `darknetra_api.security`, store a complete envelope,
and route full-value access through the audited reveal service.

## Fields covered by this boundary

The following fields require this boundary when a Plan 03 or later model stores them:

| Field | Required handling |
| --- | --- |
| Source locators | Encrypt the full locator. Store an HMAC blind index only when the feature needs equality lookup or deduplication. Default responses may return a redacted display value or a presence flag, not the envelope or plaintext. |
| Authority references | Encrypt references to warrants, approvals, legal authorities, case authorities, and related authorization records. Do not place the reference in logs, audit metadata, search indexes, or ordinary responses. |
| Policy-sensitive analyst notes and rationales | Encrypt the note or rationale whenever the owning policy marks it sensitive. The model must preserve that policy decision with the record so later serializers cannot infer that the text is public. |
| Custody notes | Encrypt free-text custody, transfer, handling, exception, and storage notes. Keep non-sensitive timestamps, actor IDs, action codes, and integrity hashes in separate structured fields when policy permits. |
| Contacts | Encrypt contact values, including email addresses, telephone numbers, messaging handles, and other direct contact identifiers. Use a purpose-specific blind index only for a defined equality lookup. |
| Policy-restricted wallets | Encrypt the full wallet value when policy restricts it. Keep unrestricted network or asset type metadata separate. Do not expose the full value through general indicator serialization. |

The owning feature may apply this boundary to more fields. It may not remove a field from this list
without an approved policy and architecture change.

## Write path

1. Normalize plaintext only when the owning feature has a documented normalization rule. The
   encryption helper does not normalize input.
2. Choose a stable purpose that names the owning resource and field, such as `source.locator`,
   `source.authority_reference`, `evidence.custody_notes`, or `contact.email`. Do not reuse one
   purpose for unrelated fields.
3. Use the stable owning resource ID as `resource_id`. The same purpose and resource ID must reach
   the reveal and rotation paths.
4. Call `SensitiveFieldCrypto.encrypt(plaintext, purpose=..., resource_id=...)`.
5. Call `pack_envelope` and persist `key_version`, `nonce_b64`, and `ciphertext_b64` as three
   explicit columns or as one validated JSON object.
6. If the feature needs equality lookup, call
   `SensitiveFieldCrypto.blind_index(normalized_plaintext, purpose=...)` and persist the returned
   HMAC-SHA-256 digest separately. Never use raw SHA-256 for a low-entropy sensitive value.
7. Drop the local plaintext reference after the write or redaction operation. Do not include
   plaintext, key material, nonces, ciphertext, or blind indexes in logs or audit metadata.

`SensitiveFieldCrypto` uses AES-256-GCM and a fresh 12-byte random nonce. Its authenticated
associated data is `darknetra:{purpose}:{resource_id}:{key_version}`. Authentication fails if a
caller changes the purpose, resource ID, key version, nonce, or ciphertext. Each envelope records
the non-secret key version that decrypts it.

The blind index uses HMAC-SHA-256 over `purpose + NUL + plaintext` with a dedicated 32-byte key.
The runtime rejects encryption-key reuse across versions and rejects reuse of any encryption key
as the blind-index key.

## Persistence and serialization

`pack_envelope` and `unpack_envelope` validate the envelope shape without accepting a crypto
service. They cannot decrypt. ORM models must not define hybrid properties, descriptors, Pydantic
serializers, or convenience accessors that decrypt during attribute access, representation, or
ordinary response serialization.

Default response models must omit plaintext and all envelope internals. When a screen needs a
limited value, an authorized service may decrypt and immediately pass the local plaintext to
`redact_for_display`. The helper supports email, phone, wallet, onion, and complete-secret
redaction. A display redaction is not suitable for equality lookup or persistence.

## Full-value reveal

The feature that owns the encrypted field must bind four request-scoped dependencies with
`bind_sensitive_reveal_context`: a case-scoped provider, a field-specific permission predicate,
the runtime crypto service, and the request ID. `reveal_sensitive_value` then enforces this order:

1. Require `CASE_READ` access to the case.
2. Require a trimmed reveal reason from 10 through 500 characters.
3. Load the field through the owning provider. A missing or cross-case resource returns the
   repository-standard not-found result.
4. Resolve persisted case membership roles, intersect them with the actor's current global roles,
   and reject an empty or viewer-only effective role set.
5. Run the owning feature's resource and field permission predicate.
6. Decrypt with purpose `{resource_type}.{field_name}` and the requested resource ID.
7. Append `SENSITIVE_VALUE_REVEALED` with actor, case, resource, field name, reason, and request ID.
   The audit event does not contain plaintext, ciphertext, nonces, blind indexes, or keys.
8. Commit the audit event before returning plaintext to the explicit response path.

An HTTP reveal endpoint must add `Cache-Control: no-store`. General read endpoints must not call
the reveal service. A feature must not catch a reveal failure and fall back to direct decryption.

## Runtime keys

Supply keys at process start through the approved runtime secret channel:

- `DARKNETRA_FIELD_KEYRING_B64_JSON` maps version names such as `v1` and `v2` to Base64 values that
  each decode to 32 bytes.
- `DARKNETRA_FIELD_ACTIVE_KEY_VERSION` selects the version used for new writes.
- `DARKNETRA_FIELD_BLIND_INDEX_KEY_B64` supplies the separate 32-byte HMAC key.
- `DARKNETRA_FIELD_KEY_V1_B64` remains a migration input for the original single-key setup.

Do not store real keys in `.env` files, repository documents, images, PostgreSQL, logs, tickets, or
repository backups. Tests and smoke commands generate fresh keys at runtime.

## Rotation

Keep every key version referenced by live envelopes or retained backups in the runtime keyring.
`SensitiveFieldKeyring` selects the envelope's recorded version for decryption and fails on an
unknown version. `rotate_sensitive_field` returns a new active-version envelope without writing to
storage. It preserves the existing blind index unless the authorized maintenance caller explicitly
requests blind-index rotation.

The owning maintenance service must authorize rotation, process bounded restartable batches, write
each replacement transactionally, and append audit records that contain counts and versions only.
It must not rewrite immutable audit or history payloads. Follow
`docs/operations/sensitive-field-key-rotation.md` for deployment order, backup recovery, rollback,
and retirement checks.

## Plan 03 integration gate

A consuming model passes this gate only when tests show that it:

- sends every covered write through `SensitiveFieldCrypto.encrypt` and passes its result to
  `pack_envelope` before the repository persists the envelope;
- sends every stored envelope through `unpack_envelope` before an authorized service uses it;
- calls `SensitiveFieldCrypto.blind_index` with the field purpose and normalized plaintext when
  the owning feature requires equality lookup or deduplication;
- omits plaintext and envelope internals from ORM representations and ordinary API responses;
- binds a case-scoped provider and feature-specific permission predicate, then sends the full-value
  API path through `reveal_sensitive_value` so the service authorizes, decrypts, audits, commits,
  and returns the plaintext;
- exercises those owning service, repository, and API call paths in tests that invoke
  `SensitiveFieldCrypto.encrypt`, `pack_envelope`, `unpack_envelope`, `reveal_sensitive_value`, and
  `SensitiveFieldCrypto.blind_index` where equality lookup or deduplication applies; test code
  paths or parallel custom envelope, decryption, and reveal logic do not satisfy this gate; and
- supports explicit re-encryption while retaining old decryption versions required by live data
  and backups.
