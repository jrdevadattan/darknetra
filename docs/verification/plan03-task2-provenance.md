# Plan 03 Task 2 — evidence provenance schema verification

- **TDD RED commit:** `1a3708654561e1dccc0ad086eb9ea339f1478690`
- **TDD RED run:** GitHub Actions `32141452479` (`plan03/task2-red` success means the pre-implementation contract suite failed as expected)
- **Verified GREEN commit:** `06b74d7e0879a37fc1fe31904d36a5c2c387af99`
- **Verified GREEN run:** GitHub Actions `32142762384`
- **Runner:** GitHub Actions `ubuntu-latest`

| Gate | Outcome |
|---|---|
| Test-first RED contract confirmation | success |
| Alembic upgrade to `8a7f2d91c402` | success |
| Alembic downgrade to `3f21c6d4a901` | success |
| Alembic re-upgrade to `8a7f2d91c402` | success |
| Ruff repository check | success |
| Focused evidence-provenance contract suite | success |
| Complete Python regression suite | success |

## Verified boundary

- `evidence_artifacts` records case-scoped provenance, source class/type, acquisition metadata, collector, timestamps, detected media metadata, expected digests, object key, processing state, quarantine metadata, tool/version, and encrypted sensitive metadata envelopes.
- `source_locator_ciphertext`, `authority_reference_ciphertext`, and `notes_ciphertext` persist the complete Plan 03a authenticated envelope (`key_version`, nonce, ciphertext/tag) rather than plaintext.
- `EvidenceArtifactRead` excludes encrypted envelopes and the internal object key from normal API serialization.
- Preservation moves a staging artifact to `PRESERVED` exactly once and expected SHA-256/SHA-512 values cannot be rewritten through the ORM service boundary after preservation.
- `evidence_derivations` records parent-child lineage and rejects self-reference.
- `custody_events` follows the existing audit-event pattern and rejects ORM updates/deletes as append-only history.
- The PostgreSQL migration explicitly manages the evidence enum types and was verified through upgrade/downgrade/re-upgrade.

## Review notes

The implementation was compared against the Task 2 plan and the Plan 03 pre-flight interface rulings. No Critical or Important mismatch was found in the Task 2 boundary. Database-level append-only enforcement beyond the application ORM event pattern is not introduced here because the existing audit subsystem uses the same boundary; broader database hardening can be considered separately without blocking the Evidence Vault plan.

## Next task

Task 3 implements the content-addressed object-store abstraction, staging, streaming hashing, expected-hash verification, atomic promotion, deduplication, and the `evidence_store` Compose volume. Upload routes and parsers remain out of scope until their later tasks.
