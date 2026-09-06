# Plan 12 — Data model (PostgreSQL 16 + pgvector + pg_trgm)

Reference for every migration. Conventions: `id uuid PK default gen_random_uuid()`, `created_at timestamptz not null default now()`, `updated_at` where rows change; `case_id uuid not null references cases(id)` on every case-scoped table with an index; enums as Postgres `text` with a CHECK constraint (easier to extend than `CREATE TYPE`); JSON as `jsonb`; money as `numeric(12,4)`; no `ON DELETE CASCADE` anywhere except child derivatives of a deleted-in-error upload during the same transaction (never after commit).

Migrations by plan: 0001 foundation (identity, cases, audit, settings) · 0003 evidence · 0004 extraction · 0005 chunks · 0006 threads/runs · 0007 analytics/decisions/ledger · 0008 capture/policy/tool registry · 0009 monitoring · 0010 reports.

---

## Enumerations

```
global_role      ADMIN | INVESTIGATOR | VIEWER
case_role        OWNER | LEAD | ANALYST | VIEWER
case_status      OPEN | CLOSED | ARCHIVED
source_class     SYNTHETIC | SEIZED | UPLOAD | OSINT_SURFACE | OSINT_DARK | CHAIN | TELEGRAM | REPORT
origin           UPLOAD | CAPTURE | MONITOR | DERIVATIVE | REPORT
evidence_status  PROCESSING | READY | PARTIAL | QUARANTINED | FAILED | EXPIRED
evidence_kind    PDF | HTML | WARC | IMAGE | CSV | JSON | TEXT | ZIP | AUDIO | VIDEO | OFFICE | UNKNOWN
derivative_kind  TEXT | OCR | TRANSCRIPT | IMAGE_META | ROWS | MESSAGES | HTML_SAFE
custody_action   INGESTED | VERIFIED | DERIVED | VIEWED_ORIGINAL | EXPORTED | QUARANTINED | RELEASED
observation_type SUBSTANCE | SLANG | VENDOR_ALIAS | MARKETPLACE | LOCATION | SHIPPING_TERM | PACKAGING_TERM | PRICE | QUANTITY | CURRENCY | CONTACT_HANDLE | EMAIL | PHONE | PGP_KEY | PGP_FINGERPRINT | BTC_ADDRESS | ETH_ADDRESS | XMR_ADDRESS | TRON_ADDRESS | URL | ONION_LOCATOR | IMAGE_REFERENCE | SLANG_CANDIDATE
run_status       QUEUED | RUNNING | DONE | ERROR | CANCELLED | BUDGET
candidate_status PENDING | ACCEPTED | REJECTED | DEFERRED
band             WEAK | POSSIBLE | LEAD | STRONG
edge_type        CO_OCCURS | USES | POSSIBLE_SAME_OPERATOR | ANALYST_CONFIRMED_RELATED | MENTIONS_LOCATION | CONTAINS
edge_status      PENDING | CONFIRMED | REJECTED | INFO
decision_target  LINK | ACTIVITY | ALERT | FINDING
decision_value   ACCEPT | REJECT | DEFER | REQUEST_MORE_EVIDENCE
finding_kind     OBSERVED | MODEL | CANDIDATE | CONFIRMED
finding_status   DRAFT | PROMOTED | SUPERSEDED
thread_status    OPEN | CLOSED
harness          CLAUDE | OFFLINE | FAKE
message_role     USER | ASSISTANT | SYSTEM | TOOL
item_type        KEYWORD | ALIAS | WALLET | PGP_FINGERPRINT | ONION_DOMAIN | TELEGRAM_CHANNEL | IMAGE_HASH
alert_kind       NEW_HIT | TREND | WALLET_ACTIVITY | KEY_CHANGE | ONION_STATUS | IMAGE_MATCH | MONITOR_ERROR | OVERFLOW
alert_status     OPEN | ACKNOWLEDGED | DISMISSED | ESCALATED
actor_kind       USER | TOKEN | SYSTEM | MODEL
requester_kind   USER | THREAD | WATCHLIST_ITEM | SYSTEM
```

---

## Identity and access (0001)

| Table | Columns | Constraints and indexes |
|---|---|---|
| `users` | id, username text unique (citext-like: lower index), display_name, password_hash, global_role, is_active bool default true, must_change_password bool default false, failed_logins int default 0, locked_until timestamptz, created_at, updated_at | unique lower(username) |
| `sessions` | id, user_id FK, refresh_hash text unique, csrf_hash text, expires_at, revoked_at, rotated_from uuid, ip inet, user_agent text, created_at | idx(user_id), idx(expires_at) |
| `api_tokens` | id, name, owner_user_id FK, token_hash text unique, scopes text[] not null, case_id FK null, expires_at, revoked_at, last_used_at, created_at | idx(owner_user_id) |
| `case_memberships` | case_id FK, user_id FK, role case_role, added_by FK, created_at | PK(case_id, user_id); idx(user_id) |

## Cases (0001)

| Table | Columns | Constraints |
|---|---|---|
| `cases` | id, code text unique, title, status case_status default OPEN, scope_notes text, authority_ref_enc bytea, authority_ref_bidx text, source_policy jsonb not null, legal_hold bool default false, demo bool default false, created_by FK users, opened_at, closed_at, archived_at, created_at, updated_at | CHECK status; idx(status); `case_code_seq_<year>` sequences created on demand |
| `settings` | key text PK, value jsonb, updated_at, updated_by | |
| `audit_events` | id, at default now(), actor_kind, actor_id uuid, case_id uuid, thread_id uuid, run_id uuid, action text, target_type text, target_id uuid, detail jsonb, result_hash text, request_id text | idx(case_id, at desc), idx(actor_id, at desc), idx(action); **trigger forbids UPDATE/DELETE** |

## Evidence (0003)

| Table | Columns | Constraints |
|---|---|---|
| `evidence` | id, case_id, code text, sha256 text, size_bytes bigint, mime text, kind evidence_kind, original_filename text, storage_key text, source_class, origin, status, locator_enc bytea, locator_bidx text, captured_at timestamptz, requested_by_kind requester_kind, requested_by_id uuid, parent_evidence_id FK evidence, transformation text, warnings jsonb default '[]', meta jsonb default '{}', created_by_kind actor_kind, created_by_id uuid, created_at | unique(case_id, code); unique(case_id, sha256, origin) (captures of identical bytes from different origins are allowed as distinct rows? No: unique(case_id, sha256) and reuse); idx(case_id, source_class), idx(case_id, status), idx(parent_evidence_id), idx(locator_bidx) |
| `custody_events` | id, evidence_id FK, action custody_action, actor_kind, actor_id, at, hash_verified bool, note text, request_id | idx(evidence_id, at) |
| `derivatives` | id, evidence_id FK, kind derivative_kind, version int, storage_key text, status text, extractor text, extractor_version text, lang_tags text[], script_tags text[], text_len int, meta jsonb, created_at | unique(evidence_id, kind, version); idx(evidence_id) |
| `evidence_code_counters` | case_id PK, next int | used by `next_evidence_code` with `SELECT … FOR UPDATE` |

## Retrieval (0005)

| Table | Columns | Constraints |
|---|---|---|
| `chunks` | id, case_id, evidence_id FK, derivative_id FK, derivative_version int, ordinal int, kind text, text text, search_text text, span_start int, span_end int, line_no int, lang text, script text, source_class, tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED, embedding vector(1024), embedding_model text, embedded_at timestamptz, created_at | unique(derivative_id, derivative_version, ordinal); GIN(tsv); GIN(text gin_trgm_ops); HNSW(embedding vector_cosine_ops) WITH (m=16, ef_construction=64); idx(case_id, evidence_id) |

If `settings.embedding_dim` ≠ 1024, a migration alters the vector dimension (drop/recreate index).

## Extraction (0004)

| Table | Columns | Constraints |
|---|---|---|
| `taxonomy_terms` | id, canonical text, type observation_type, term text, language text, script text, note text, active bool, version int, created_at, updated_at | unique(canonical, term, language, script); idx(term) |
| `extraction_runs` | id, case_id, evidence_id null, bundle_version text, status text, stats jsonb, started_at, finished_at, error text | unique(evidence_id, bundle_version) where evidence_id not null; idx(case_id) |
| `canonical_entities` | id, case_id, type, value text, display text, first_seen_at, last_seen_at, observation_count int default 0, attrs jsonb, created_at, updated_at | unique(case_id, type, value); idx(case_id, type) |
| `observations` | id, case_id, evidence_id FK, derivative_id FK, run_id FK, type, raw text, normalized jsonb, canonical_entity_id FK null, span_start int, span_end int, line_no int, validator text, valid bool, confidence real, meta jsonb, created_at | idx(case_id, type), idx(evidence_id), idx(canonical_entity_id), idx(run_id); CHECK(span_end > span_start) |

## Threads and runs (0006)

| Table | Columns | Constraints |
|---|---|---|
| `threads` | id, case_id, title, goal, status thread_status, harness, harness_session_id text, summary text, summary_updated_at, pinned_finding_ids uuid[] default '{}', budget_usd numeric(12,4) default 2, spent_usd numeric(12,4) default 0, assignee_id FK users null, created_by, created_at, updated_at, last_message_at | idx(case_id, updated_at desc) |
| `runs` | id, thread_id FK, case_id, status run_status, harness, started_at, finished_at, cost_usd numeric(12,4), tokens_in int, tokens_out int, error jsonb, cancel_requested bool default false, replayed_from_run_id uuid, created_at | idx(thread_id, created_at); partial unique(thread_id) where status in (QUEUED, RUNNING) |
| `messages` | id, thread_id FK, run_id FK null, case_id, role message_role, blocks jsonb, text text, claims jsonb, verification jsonb, tokens_in int, tokens_out int, cost_usd numeric(12,4), harness text, at | idx(thread_id, at) |
| `tool_calls` | id, run_id FK, thread_id, case_id, seq int, tool text, args jsonb, args_hash text, policy_decision jsonb, status text, started_at, finished_at, duration_ms int, result_hash text, result_evidence_ids uuid[], error jsonb, cached bool default false, requester_kind, requester_id | idx(run_id, seq); idx(case_id, tool, started_at) |
| `run_events` | run_id FK, seq int, type text, data jsonb, at | PK(run_id, seq) |
| `replay_entries` | id, case_id, question_norm text, harness text, run_id FK, event_log jsonb, created_at | unique(case_id, question_norm, harness) |
| `rate_counters` | case_id, rate_key text, window_start timestamptz, count int | PK(case_id, rate_key, window_start) |

## Analytics, decisions, ledger (0007)

| Table | Columns | Constraints |
|---|---|---|
| `analytic_runs` | id, case_id, kind text, version text, config_digest text, status, stats jsonb, started_at, finished_at, error text | idx(case_id, kind, started_at desc) |
| `link_candidates` | id, case_id, run_id FK, subject_a_id FK canonical_entities, subject_b_id FK, score int, band, features jsonb, evidence_ids uuid[], contradictions jsonb, families text[], status candidate_status default PENDING, version int default 1, supersedes_id uuid, feature_digest text, meta jsonb, created_at | CHECK(subject_a_id < subject_b_id); unique(case_id, subject_a_id, subject_b_id, version); idx(case_id, band, status) |
| `activity_candidates` | id, case_id, run_id, evidence_id FK, score real, label text, features jsonb, status candidate_status, version int, created_at | unique(case_id, evidence_id, version) |
| `wallet_assessments` | id, case_id, address text, chain text, gnn jsonb, gnn_unavailable_reason text, sanctions jsonb, live_summary jsonb, live_summary_evidence_id FK evidence, tags text[], traceable bool, assessed_at, version int, requested_by_kind, requested_by_id | idx(case_id, address) |
| `trend_buckets` | case_id, subject_type text, subject text, day date, count int, unique_evidence_families int, unique_aliases int, unique_sources int, computed_at | PK(case_id, subject_type, subject, day) |
| `graph_edges` | id, case_id, src_entity_id FK, dst_entity_id FK, type edge_type, status edge_status, score real, families text[], candidate_id FK null, decision_id uuid null, provenance jsonb (evidence ids, counts), first_seen_at, last_seen_at, updated_at | unique(case_id, src_entity_id, dst_entity_id, type); idx(case_id, status) |
| `decisions` | id, case_id, target_type decision_target, target_id uuid, target_version int, decision decision_value, rationale text, decided_by FK users, at, superseded_by uuid, request_id | unique(case_id, target_type, target_id, target_version) where superseded_by is null; idx(case_id, at desc) |
| `findings` | id, case_id, thread_id FK null, title, claim text, kind finding_kind, evidence_ids uuid[], method text, method_version text, confidence real, status finding_status, version int, supersedes_id uuid, source_message_id uuid, claim_index int, decision_id uuid, created_by, at | idx(case_id, status) |
| `ledger_nodes` | case_id, node_index int, txid text, timestep int, label int, features real[] (length 102 CHECK), imported_at | PK(case_id, node_index) |
| `ledger_edges` | case_id, src int, dst int | PK(case_id, src, dst) |
| `ledger_addresses` | case_id, address text, chain text, node_index int, tag text | PK(case_id, address); idx(case_id, node_index) |

## Capture, policy, tool registry (0008)

| Table | Columns | Constraints |
|---|---|---|
| `tool_registry` | name text PK, kind text, server text, lane text, requires_network bool, source_class text, policy_tags text[], rate_key text, rate_cap_per_hour int, enabled bool default true, health jsonb, last_health_at, updated_at | |
| `policy_decisions` | id, case_id, tool text, allow bool, rule text, reason text, args_hash text, requester_kind, requester_id, at | idx(case_id, at desc); (denials also produce audit events) |

## Monitoring (0009)

| Table | Columns | Constraints |
|---|---|---|
| `watchlists` | id, case_id, name, active bool default true, created_by, created_at | idx(case_id) |
| `watchlist_items` | id, watchlist_id FK, case_id, type item_type, value text, value_norm text, variants text[], sources text[], interval_seconds int, active bool, note text, state jsonb default '{}', last_run_at, next_run_at, created_by, created_at, updated_at | unique(case_id, type, value_norm); idx(next_run_at) where active |
| `monitor_runs` | id, item_id FK, case_id, started_at, finished_at, status text, manual bool, sources_run jsonb, new_hits int, errors jsonb | idx(item_id, started_at desc) |
| `monitor_hits` | id, run_id FK, item_id FK, case_id, evidence_id FK null, url_hash text, content_hash text, relevance real, alertable bool, reasons jsonb, alert_id uuid, at | unique(item_id, content_hash); idx(case_id, at desc) |
| `monitor_seen_urls` | item_id, url_hash text, first_seen_at, last_seen_at | PK(item_id, url_hash) |
| `alerts` | id, case_id, kind alert_kind, title, summary text, evidence_ids uuid[], item_id FK null, diversity jsonb, config_version text, status alert_status default OPEN, finding_id uuid, assigned_to uuid, at, handled_at, handled_by uuid, decision_id uuid | idx(case_id, status, at desc) |

## Reports (0010)

| Table | Columns | Constraints |
|---|---|---|
| `reports` | id, case_id, version int, evidence_id FK (the stored pack), storage_key_md text, storage_key_html text, sha256 text, generated_by FK users, at, includes jsonb, claim_check jsonb, redaction jsonb, status text, error text | unique(case_id, version) |

---

## Invariants enforced in the database

- `audit_events`: trigger raises on UPDATE/DELETE.
- `evidence`: no application code path issues DELETE; a DB role used by the API lacks DELETE on `evidence`, `custody_events`, `derivatives`, `decisions`, `audit_events`, `reports` (grant matrix in plan 14).
- `link_candidates`: `subject_a_id < subject_b_id`.
- `runs`: at most one QUEUED/RUNNING per thread (partial unique index).
- `observations`: `span_end > span_start`; application verifies `text[span] == raw` before insert.
- `chunks.embedding` nullable: lexical search never depends on it.

## Retention

`cases.legal_hold=true` blocks any retention job. Retention (when `retention_days` set) sets `evidence.status=EXPIRED` and deletes derivative files from the vault only; rows, hashes and manifests stay.
