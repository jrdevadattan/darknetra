# Sensitive-field key rotation

Sensitive-field encryption keys are runtime secrets. They are not stored in PostgreSQL,
application images, repository files, logs, or repository backup archives. Envelopes carry a
non-secret key version so the API can select the exact key that created each ciphertext.

## Runtime configuration

`DARKNETRA_FIELD_KEYRING_B64_JSON` is a JSON object mapping version identifiers to Base64 values
that each decode to exactly 32 bytes. `DARKNETRA_FIELD_ACTIVE_KEY_VERSION` must name one entry in
that object. `DARKNETRA_FIELD_BLIND_INDEX_KEY_B64` is a separate 32-byte key and must not reuse an
encryption key.

During migration from the original single-key configuration,
`DARKNETRA_FIELD_KEY_V1_B64` may remain configured. If the JSON keyring also contains `v1`, both
values must match or sensitive-field crypto construction fails closed. Do not put real values in
`.env.example`, documentation, shell history, tickets, or the repository.

## Rotation procedure

1. Generate the new 32-byte encryption key in the approved secret manager or HSM and assign the
   next version, such as `v2`. Record the non-secret version and change approval separately.
2. Add the new version to every runtime keyring while retaining all versions still referenced by
   live data or retained backups. Deploy first with the old version still active and confirm every
   process loads the complete keyring.
3. Change `DARKNETRA_FIELD_ACTIVE_KEY_VERSION` to the new version and restart the affected
   processes. New writes now use the new version; old envelopes remain decryptable by their stored
   version.
4. Take a database backup under the normal backup policy before bulk maintenance. Back up or escrow
   the required key versions through the approved secret-management recovery system, separately
   from the database/repository archive. A ciphertext backup is unrecoverable without every key
   version it references.
5. Run re-encryption only as an authorized offline/admin maintenance job for the owning model. For
   each current mutable record, decrypt using the envelope's recorded version and write the fresh
   active-version envelope transactionally. Use bounded, restartable batches and record counts and
   key versions, never plaintext, ciphertext, nonces, blind indexes, or key material.
6. Preserve the stored blind index when only the encryption key changes. Recompute it only during a
   separately approved blind-index-key rotation, and rebuild every affected equality index in the
   same controlled maintenance window.
7. Never update or re-encrypt immutable audit/history payloads in place. If a historical payload
   requires a new representation, append a new auditable maintenance event or use the owning
   subsystem's explicit versioned migration design.
8. Verify that sampled records decrypt through the authorized service, all current mutable records
   use the active version, equality lookups still work, and restore/decryption succeeds in a
   disposable recovery environment before closing the change.

The `SensitiveFieldKeyring` and `rotate_sensitive_field` primitives do not write to storage. The
owning model's maintenance service is responsible for authorization, transaction boundaries,
restart checkpoints, and audit events.

## Key retirement and rollback

Do not remove an old key merely because current rows were re-encrypted. Retain it until scans prove
that no live envelope references it and every backup that may reference it has either expired or
been restored and re-encrypted under an approved recovery procedure. Perform a restore drill before
destruction and follow the organization's cryptographic key-destruction approval process.

Rollback means restoring the prior active-version selection while keeping both versions loaded.
Already rotated envelopes require the new key; never roll back by deleting it or by rewriting audit
history.
