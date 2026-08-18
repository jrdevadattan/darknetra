# SDD ledger — plan: docs/superpowers/plans/2026-08-17-03-evidence-vault-ingestion.md

## Preconditions

- Plan 01 verification: complete.
- Plan 02 verification: complete.
- Mandatory Plan 03a encryption boundary: complete and green.
- Working branch: `testing-codex`; `main` remains stable.

## Pre-flight interface scan

| Producer task | Consumer task | Shared file/interface | Finding and ruling |
|---|---|---|---|
| Plan 03a | Plan 03 Task 2 | Sensitive evidence metadata | **Ruling:** Evidence models store complete `key_version`, `nonce_b64`, and `ciphertext_b64` fields plus optional blind index/redaction. The older singular `*_ciphertext` wording does not override the mandatory tested envelope boundary. Cost if wrong: migration adjustment before real data. |
| Task 1 | Tasks 4 and 8 | Durable jobs + Celery | **Ruling:** PostgreSQL job rows are authoritative; Redis/Celery carry delivery only. Queue loss never deletes job history. Task 4 creates the idempotent row before dispatch; Task 8 owns state transitions. |
| Task 2 | Tasks 5–8 | Evidence/derivation schema | **Ruling:** Archive members and parser outputs are child `EvidenceArtifact` records with their own content-addressed objects. Unique derivation identity prevents duplicate lineage across retries. |
| Task 3 | Tasks 4–9, 11 | Object-store API | **Ruling:** Clients submit evidence IDs only. Object keys remain server-side, are grammar validated, and never appear as filesystem links or credentials in the browser. |
| Task 4 | Task 8 | Post-commit dispatch | **Ruling:** Object promotion and evidence/audit/custody metadata commit before delivery. Dispatch failure leaves a durable retryable job rather than rolling back a successfully preserved original. |
| Task 5 | Task 8 | ZIP members and chat export | **Ruling:** ZIP members stream directly into child content-addressed objects; there is no shared extraction directory. Nested archives are rejected in the MVP. |
| Task 6 | Task 10–11 | HTML preview | **Ruling:** Parser output is inert sanitized HTML/text only. Content routes add restrictive headers; the UI never embeds uncontrolled original HTML. |
| Task 7 | Task 8 | Image/PDF derivative state | **Ruling:** Image-only PDF becomes `TEXT_NOT_AVAILABLE` and may still be `READY` for metadata/preview processing; OCR is explicitly out of scope. |
| Task 8 | Task 9 | Integrity mismatch | **Ruling:** Processing refuses artifacts in `INTEGRITY_MISMATCH`; expected hashes are immutable and never reconciled to observed tampered bytes. |
| Task 10 | Task 11 | Restricted reveal/content access | **Ruling:** Metadata full reveal uses Plan 03a audited reveal. Original-byte access uses the audited content endpoint with download-safety headers. They are separate security events. |
| Task 11 | Task 12 | Content security | **Ruling:** Unknown or executable content is attachment-only. Safe inline preview is restricted to generated derivatives with `nosniff` and restrictive CSP. |
| Task 12 | Task 13 | Security regression evidence | **Ruling:** Adversarial fixtures are generated in tests and contain no real criminal or chat data. Final verification must include them and a one-byte tamper experiment. |

## Task status

- Task 1: complete — durable PostgreSQL job boundary, Redis/Celery delivery, migration, and worker smoke verified at `5bd0f473fee8a7d2279025a18f43eb306e265e42`.
- Task 2: complete — evidence provenance, encrypted sensitive metadata, immutable expected digests, derivation lineage, append-only custody, safe read schema, and migration cycle verified by GREEN run `32142762384`; record: `docs/verification/plan03-task2-provenance.md`.
- Task 3: pending.
- Task 4: pending.
- Task 5: pending.
- Task 6: pending.
- Task 7: pending.
- Task 8: pending.
- Task 9: pending.
- Task 10: pending.
- Task 11: pending.
- Task 12: pending.
- Task 13: pending.
