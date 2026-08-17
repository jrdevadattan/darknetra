# DARKNETRA Implementation Plan Index

The approved design spans multiple independently testable subsystems. To keep agentic work reviewable and avoid one unmanageable mega-plan, implementation is split into ordered plans. Each plan must leave the repository in a working, testable state before the next begins.

## Execution order

1. `2026-08-17-01-foundation-dashboard.md` — monorepo/tooling/Docker foundation; import and aggressively clean the approved shadcn admin dashboard; DARKNETRA navigation and route shell; frontend test/build baseline.
2. `2026-08-17-02-api-auth-cases.md` — FastAPI/PostgreSQL foundation, migrations, authentication, case-scoped RBAC, case lifecycle, frontend API integration.
3. `2026-08-17-02a-auth-session-decisions.md` — normative auth supplement fixing the JWT library/signing, cookie names/attributes, refresh rotation, CSRF mechanism, lockout and CORS choices used while executing Plan 02.
4. `2026-08-17-03a-sensitive-field-encryption.md` — mandatory application-level encryption, blind indexes, audited reveal, and key-version boundary for sensitive case/evidence metadata.
5. `2026-08-17-03-evidence-vault-ingestion.md` — content-addressed immutable evidence store, manifests, hashes, custody, safe WARC/HTML/TXT/JSON/CSV/ZIP/image/PDF ingestion and quarantine flows. This plan consumes the 03a encryption boundary for sensitive metadata.
6. `2026-08-17-04-extraction-indicators.md` — normalization, Hindi/Punjabi/Hinglish handling, domain entities, PGP/crypto/contact/price/quantity validation, source-linked spans.
7. `2026-08-17-05-activity-correlation.md` — transactional activity candidates, image matching, bounded stylometry, explainable alias fusion, contradiction logic and analyst decisions.
8. `2026-08-17-06-graph-trends-reports.md` — transactional outbox, Neo4j projection, NarcoGraph UI, timeline, deduplicated trend alerts, Markdown/PDF investigation packs.
9. `2026-08-17-07-evaluation-offline-demo.md` — synthetic/replay ground-truth corpus, hard negatives, evaluation metrics, offline packaging, CI/security checks and finale demo hardening.
10. `2026-08-17-08-optional-lawful-collector.md` — policy-gated read-only public-source/Tor collection adapter. This plan is optional and MUST NOT be started before the core plans above are stable.

## Global rules

- Work on `testing-codex`; `main` remains stable.
- TDD for independently testable behavior.
- No task is complete without fresh verification output.
- PostgreSQL is authoritative; Neo4j is rebuildable.
- Original evidence is immutable.
- Plan 02 authentication must also follow the normative 02a supplement; open choices in the older Plan 02 wording do not override 02a.
- Sensitive plaintext uses the 03a encryption boundary; naming a database field `ciphertext` is not sufficient without the tested encryption service.
- Imported content is untrusted.
- LLM output is never evidence and cannot directly create accepted identity relationships.
- Core product and demo must work without live Tor, public internet, a cloud LLM, or GPU access.
- Preserve the MIT attribution for `arhamkhnz/next-shadcn-admin-dashboard`.
- Do not add features that buy drugs, contact sellers, authenticate to criminal services, bypass encryption/access controls, or perform unauthorized access.

Read the approved design at `docs/superpowers/specs/2026-08-17-darknetra-dashboard-monorepo-design.md`, ADR-0001, this index, the current plan, and any indexed normative supplement immediately following that plan before execution.