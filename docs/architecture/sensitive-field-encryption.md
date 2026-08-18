# Sensitive-field encryption and audited reveal boundary

Plan 03a establishes the application-level protection used by Evidence Vault metadata and later analytic records. PostgreSQL remains authoritative for encrypted envelopes, blind indexes and audit history, but it never receives the encryption or blind-index keys.

## Protected data classes

The following values must use this boundary whenever policy marks them sensitive:

- source locators, including onion URLs, public-source URLs and imported account/channel identifiers;
- authority references and acquisition authorizations;
- analyst notes, rationales and link-review explanations containing restricted operational context;
- custody notes;
- email addresses, telephone numbers and other contact indicators;
- policy-restricted wallet or account values;
- future fields explicitly classified as sensitive by their owning feature.

A field name containing `ciphertext` is not sufficient. The owning service must use `SensitiveFieldCrypto` or `SensitiveFieldKeyring`, persist the complete validated envelope, expose only a redaction by default, and route full reveal through the audited service.

## Cryptographic design

DARKNETRA uses AES-256-GCM from the `cryptography` library. No custom cipher, block mode, key derivation function or authentication construction is implemented.

Each encrypted value contains:

```text
key_version
nonce_b64
ciphertext_b64
```

The 96-bit nonce is generated independently with the operating system CSPRNG for every encryption. The GCM authentication tag is carried within `ciphertext_b64`. Re-encrypting identical plaintext therefore produces different nonce and ciphertext values.

Associated authenticated data is:

```text
darknetra:<purpose>:<resource_id>:<key_version>
```

This binds the ciphertext to its field purpose, owning resource identifier and key version. Moving a stored envelope between resources or purposes causes authenticated decryption to fail. Purposes and identifiers are validated before use; context separators and NUL characters are rejected.

Decryption errors are deliberately generic. Logs, exceptions and representations do not contain plaintext, keys, nonces or ciphertext values beyond explicitly redacted diagnostics.

## Runtime keys

Encryption and blind indexing use different 256-bit keys.

| Setting | Purpose |
|---|---|
| `DARKNETRA_FIELD_KEY_V1_B64` | Single-version compatibility input for the initial deployment |
| `DARKNETRA_FIELD_KEYRING_B64_JSON` | Optional secret JSON object mapping key version to base64-encoded 32-byte keys |
| `DARKNETRA_FIELD_ACTIVE_KEY_VERSION` | Version used for new encryption and explicit re-encryption |
| `DARKNETRA_FIELD_BLIND_INDEX_KEY_B64` | Separate 32-byte HMAC key for equality/deduplication indexes |

`DARKNETRA_FIELD_KEYRING_B64_JSON` is supplied only through a secret manager or mounted secret channel. It is intentionally not populated in `.env.example`, documentation examples, CI artifacts or repository fixtures. When the JSON keyring is absent, the v1 compatibility input is used.

Every decoded key must be exactly 32 bytes. The active version must exist in the runtime keyring. Unknown historical key versions fail closed and are never decrypted with the active key as a fallback.

## Equality and deduplication indexes

Where an owning feature needs exact equality or deduplication, it stores:

```text
HMAC-SHA-256(blind_index_key, purpose || NUL || normalized_plaintext)
```

The owning feature defines and tests normalization before calling `blind_index`. Examples include case-folding an email domain or canonicalizing a validated wallet representation. Low-entropy values are never indexed with unkeyed SHA-256.

Blind indexes are purpose scoped. The same normalized value used as a contact and as a source locator does not produce the same index. The blind-index key is independent from every encryption key.

## Persistence boundary

`pack_envelope` and `unpack_envelope` are the only generic persistence helpers. They validate the required fields, base64 encoding, 12-byte nonce and minimum GCM ciphertext/tag length. They do not decrypt.

Owning models may store the envelope as explicit columns or as a constrained JSON object. Ordinary ORM properties and Pydantic response schemas must not automatically decrypt and must omit envelope internals. API list/detail responses normally expose only policy-approved redactions.

Supported display redactions include email, telephone, wallet, onion host and fully masked general values. Redaction occurs only while plaintext is already inside an authorized service call; the redacted display value is not a substitute for encryption.

## Audited reveal flow

Full reveal follows this boundary:

```text
validate reason
    -> resolve owning resource definition
    -> enforce case visibility and SENSITIVE_VALUE_REVEAL permission
    -> load the explicitly registered encrypted field
    -> decrypt with purpose/resource AAD
    -> append SENSITIVE_VALUE_REVEALED audit event
    -> return plaintext only to the requesting response path
```

Reveal reasons are stripped and must contain 10 through 500 characters. The audit event contains actor, case, resource type and identifier, field name, reason, request identifier and non-secret key version. It never contains plaintext, blind-index input, ciphertext or keys.

The owning resource registers an explicit resolver and field-to-purpose map with `SensitiveValueRegistry`. The generic reveal service does not use unrestricted ORM reflection and cannot decrypt arbitrary columns by name.

The HTTP endpoint that exposes a revealed value must set `Cache-Control: no-store`, avoid intermediary caching, and must not place plaintext in URLs, logs, analytics, browser storage or query-cache persistence. VIEWER does not receive reveal permission. Cross-case inaccessible resources use the same repository-standard `404 resource not found` outcome as unknown resources.

## Key rotation procedure

Rotation is explicit maintenance, never an implicit ORM side effect.

1. Back up the current database and verify that every historical encryption key needed by retained data is recoverable from the external secret-management backup. Keys are never placed in the database backup or repository archive.
2. Add the new version and key to `DARKNETRA_FIELD_KEYRING_B64_JSON` while retaining all old versions.
3. Change `DARKNETRA_FIELD_ACTIVE_KEY_VERSION` to the new version and restart the authorized maintenance/application context.
4. New values immediately use the active version. Old values remain decryptable because their version remains in the runtime keyring.
5. Run an owner-specific maintenance operation that reads one authorized envelope, authenticates/decrypts with its historical version and writes a newly encrypted envelope using the active version. The operation must preserve record history and emit an audit/maintenance event in the owning feature.
6. Recompute the blind index only when the blind-index key is intentionally rotated. Ordinary encryption-key rotation preserves the existing blind index.
7. Verify counts, decryptability and backups before removing any historical key from online configuration. Removing a key while retained envelopes still reference it makes those values unavailable by design.

`SensitiveFieldKeyring.reencrypt` provides the cryptographic primitive. It does not scan tables, commit database changes or rewrite audit history.

## Backup and disaster recovery

A database/object-store backup without the external key backup cannot recover protected metadata. A key backup without the database does not reveal data. Operations must therefore maintain separate, access-controlled and tested backups for:

- database and evidence-store state;
- versioned encryption keys;
- blind-index key;
- key-version inventory and rotation records.

Restore drills must verify at least one retained envelope per key version without exporting the plaintext into logs or general-purpose artifacts.

## Failure behavior

- malformed base64, nonce length or ciphertext length: reject before decryption;
- wrong purpose/resource or modified nonce/ciphertext: authenticated decryption failure;
- unknown key version: typed fail-closed error;
- missing runtime key: startup/service configuration failure when protected functionality is invoked;
- missing case membership or invisible case: repository-standard not-found result;
- insufficient effective permission: authorization denied;
- invalid reveal reason: request rejected before decryption or audit insertion;
- audit/database failure: the owning transaction must roll back rather than reporting a successful reveal mutation trail.

## Plan 03 integration contract

Evidence Vault models must use this boundary for source locator, authority reference and sensitive notes. They should persist a redacted display value where useful, a purpose-scoped blind index only where equality lookup is needed, and the versioned envelope fields. Evidence content bytes remain protected by Evidence Vault access controls and object storage; this boundary specifically protects sensitive structured metadata.
