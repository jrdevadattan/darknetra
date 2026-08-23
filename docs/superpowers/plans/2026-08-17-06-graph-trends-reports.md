# DARKNETRA Graph Projection, Timeline, Trends, and Investigation Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rebuildable Neo4j investigation projection, evidence-provenance graph UI, case timeline, deduplication-aware emerging-activity alerts, and deterministic evidence-linked Markdown/PDF investigation packs.

**Architecture:** Business transactions write PostgreSQL plus a transactional outbox row in one commit. A projector consumes outbox rows idempotently and writes derived Neo4j nodes/edges; graph loss is recoverable by full rebuild from PostgreSQL. Timeline and trends remain authoritative PostgreSQL queries/materializations. Reports are rendered from approved structured state, registered as new hashed evidence-like output artifacts, and never depend on an LLM.

**Tech Stack:** PostgreSQL, SQLAlchemy, Celery, Neo4j Community 5.26 LTS, official Neo4j Python driver, Cytoscape.js, Recharts, Jinja2, WeasyPrint, Markdown, pytest, Playwright.

## Global Constraints

- Begin after Plan 05 verification.
- PostgreSQL is authoritative. Never dual-write Neo4j in request/business transactions.
- Neo4j may be deleted and rebuilt without authoritative data loss.
- Every projected edge capable of influencing an investigation view carries evidence/candidate/decision provenance identifiers and first/last seen where applicable.
- Pending analytic candidates are visually/semantically distinct from analyst-confirmed relationships.
- Graph user layout/preferences are not authoritative case evidence.
- Trend counts are deduplicated and include source/alias diversity; one mirrored page or spammy alias must not dominate alerts.
- Reports distinguish observed facts, model/analytic outputs, pending leads, analyst-confirmed findings, contradictions, and limitations.
- Every factual report statement references evidence IDs; every analytic statement identifies method/version.
- Reports contain no active scripts/links and are themselves hashed/registered.
- Optional LLM summaries, if added, remain draft notes with evidence-ID validation and are not required for report generation.

---

### Task 1: Add transactional outbox schema and writer

**Files:**
- Create `apps/api/darknetra_api/models/outbox.py`.
- Create `apps/api/darknetra_api/services/outbox.py`.
- Modify relevant Plan 05 mutation services to append outbox events.
- Create migration/tests.

**Interfaces:**
- `outbox_events(id, aggregate_type, aggregate_id, event_type, payload_json, created_at, published_at, attempts, last_error)`.
- Event types versioned, e.g. `case.v1`, `evidence.v1`, `entity.v1`, `link_candidate.v1`, `link_decision.v1`, `vendor_cluster.v1`, `activity_candidate.v1`.

- [ ] **Step 1: Write transaction rollback test** showing business mutation and outbox append either both commit or both roll back.
- [ ] **Step 2: Implement outbox writer** accepting JSON-safe IDs/versioned payload only; do not serialize ORM objects.
- [ ] **Step 3: Add idempotency key/event ID** unique for mutation/version.
- [ ] **Step 4: Backfill/rebuild path must not rely exclusively on old outbox history**; full projector reads authoritative tables.
- [ ] **Step 5: Commit** `feat: add transactional graph outbox`.

---

### Task 2: Add Neo4j Compose service and projector service boundary

**Files:**
- Modify Compose/env.
- Create `services/graph-projector/pyproject.toml`.
- Create `services/graph-projector/darknetra_graph/**`.
- Create tests.

**Interfaces:**
- Projector commands: `project-pending`, `rebuild-case <case_id>`, `rebuild-all`.

- [ ] **Step 1: Add Neo4j service** on internal `app` network; host browser/Bolt ports only in dev Compose if needed. Credentials from environment, no defaults committed.
- [ ] **Step 2: Write failing connectivity/config tests** and verify projector can start when Neo4j unavailable without corrupting outbox state.
- [ ] **Step 3: Implement driver wrapper** with bounded retry/backoff and explicit transaction functions.
- [ ] **Step 4: Mark outbox `published_at` only after successful Neo4j transaction**; failed projection increments attempt/error and is retriable.
- [ ] **Step 5: Commit** `feat: add rebuildable Neo4j projector service`.

---

### Task 3: Implement graph schema, constraints, and idempotent projection

**Files:**
- Create graph mapping modules/tests.

**Interfaces:**
- Node labels: `Case`, `Evidence`, `Source`, `VendorAlias`, `VendorCluster`, `Listing`, `Message`, `Drug`, `Wallet`, `PgpKey`, `Contact`, `Image`, `Location`, `Alert`.
- Relationship types include `CONTAINS`, `DERIVED_FROM`, `POSTED`, `SENT`, `MENTIONS`, `USES`, `CLAIMS_LOCATION`, `POSSIBLE_SAME_OPERATOR`, `ANALYST_CONFIRMED_RELATED`, `TRIGGERED`.

- [ ] **Step 1: Create uniqueness constraints** on stable PostgreSQL IDs/projection keys, not display names.
- [ ] **Step 2: Write idempotency test** applying same event twice produces no duplicate node/edge.
- [ ] **Step 3: Write update test** later PostgreSQL version updates projected properties while retaining evidence provenance.
- [ ] **Step 4: `POSSIBLE_SAME_OPERATOR` edge contains candidate ID, score, signal contributions, analyst state, run version; accepted relation is separate explicit edge or status property driven by decision.
- [ ] **Step 5: Do not encode guilt/criminal labels in graph schema.
- [ ] **Step 6: Commit** `feat: project evidence provenance graph`.

---

### Task 4: Implement full case/all rebuild and projection parity tests

**Files:**
- Create rebuild modules/tests.

- [ ] **Step 1: Build synthetic authoritative fixture** with evidence/entities/link/decision/cluster.
- [ ] **Step 2: Project incrementally; export normalized graph snapshot.
- [ ] **Step 3: Drop Neo4j database/clear nodes; run full case rebuild; export snapshot.
- [ ] **Step 4: Assert normalized snapshots equal**, excluding non-authoritative layout/runtime timestamps.
- [ ] **Step 5: Add system health projection lag metric** oldest unpublished outbox age/count.
- [ ] **Step 6: Commit** `test: prove Neo4j projection is rebuildable`.

---

### Task 5: Build graph query API with bounded exploration

**Files:**
- Create API graph schemas/routes/service/tests.

**Interfaces:**
- `GET /api/v1/cases/{case_id}/graph?focus=&depth=1&include_pending=true`.
- Maximum default one hop; hard max depth 2 in interactive API; bounded node/edge counts.

- [ ] **Step 1: Write cross-case authorization and cardinality-limit tests**.
- [ ] **Step 2: Return graph DTO** nodes `{id,type,label,status,metadata}` edges `{id,source,target,type,status,confidence,provenance}`.
- [ ] **Step 3: Edge provenance endpoint** returns supporting evidence IDs/candidate/decision references, never unrestricted object locators.
- [ ] **Step 4: Degrade gracefully**: if Neo4j unavailable return typed `GRAPH_UNAVAILABLE` while case/evidence APIs remain operational.
- [ ] **Step 5: Commit** `feat: expose bounded investigation graph API`.

---

### Task 6: Replace NarcoGraph UI shell with Cytoscape investigator graph

**Files:**
- Create `apps/web/src/features/graph/**`.
- Replace case graph route; tests/E2E.

- [ ] **Step 1: Write tests** for node/edge status labels, provenance drawer, pending vs accepted textual legend, keyboard table alternative.
- [ ] **Step 2: Implement Cytoscape canvas** with deterministic initial layout, one-hop expansion, filters by node type/link status/confidence.
- [ ] **Step 3: Clicking edge opens provenance drawer** and evidence links; never hide reasoning behind hover only.
- [ ] **Step 4: Save user layout only client/user preference** and ensure saved positions never enter report evidence.
- [ ] **Step 5: Add accessible graph table** listing source/relationship/target/status/provenance for keyboard/screen-reader users.
- [ ] **Step 6: E2E** focus alias -> expand -> open PGP/image link provenance -> navigate evidence.
- [ ] **Step 7: Commit** `feat: add evidence provenance NarcoGraph`.

---

### Task 7: Implement authoritative case timeline

**Files:**
- Create timeline query/service/API.
- Create `apps/web/src/features/timeline/**`.

**Interfaces:**
- Timeline event types: evidence capture/ingest, observation first/last seen, analytic run, candidate creation, analyst decision, cluster change, alert, report generation.

- [ ] **Step 1: Write ordering tests** with identical timestamps using stable secondary ID order.
- [ ] **Step 2: Preserve UTC canonical timestamp plus original timezone/context fields where known.
- [ ] **Step 3: Filter by alias/cluster/entity/source/event type/time.
- [ ] **Step 4: UI visually groups date ranges but exposes exact timestamp/detail on focus/click; no inferred timezone.
- [ ] **Step 5: Commit** `feat: add case investigation timeline`.

---

### Task 8: Implement deduplication-aware trend aggregation

**Files:**
- Create `apps/api/darknetra_api/analytics/trends.py`.
- Add aggregation tables/materialization migration as necessary.
- Create tests.

**Interfaces:**
- Per time bucket: term/entity count, unique evidence families, unique aliases, unique sources, listing/message count, related cluster count.

- [ ] **Step 1: Write mirror/duplicate tests**: identical/near-identical evidence family counted once for trend volume where policy says dedupe; source diversity remains transparent.
- [ ] **Step 2: Write spam test**: same alias repeats term many times; diversity gate prevents alert solely from one actor.
- [ ] **Step 3: Implement rolling baseline z-score**:

```text
Z_t = (x_t - rolling_mean) / max(rolling_std, 1)
```

plus configurable minimum absolute current count and minimum source/alias diversity.

- [ ] **Step 4: Use explicit time buckets** daily by default; all bucket boundaries UTC.
- [ ] **Step 5: Store trend configuration/version** with each generated alert candidate.
- [ ] **Step 6: Commit** `feat: aggregate deduplicated investigation trends`.

---

### Task 9: Implement emerging activity/term alert lifecycle

**Files:**
- Create alert model/service/routes/tests if not already complete.
- Create `apps/web/src/features/alerts/**` and global trends UI.

**Interfaces:**
- Alert states `OPEN`, `ACKNOWLEDGED`, `DISMISSED`, `RESOLVED`; dispositions audited.

- [ ] **Step 1: Write planted-trend tests**: gradual baseline then spike across multiple source groups triggers; 1->2 tiny jump does not; one-source spam does not.
- [ ] **Step 2: Alert includes baseline/current counts, z-score, source/alias/cluster diversity, evidence query references, config version.
- [ ] **Step 3: Implement case Alerts UI** time series + evidence drilldown + disposition.
- [ ] **Step 4: Implement `/intelligence/trends`** aggregated across cases only for globally authorized roles; no cross-case leakage to ordinary analysts.
- [ ] **Step 5: Commit** `feat: add evidence backed emerging trend alerts`.

---

### Task 10: Implement deterministic investigation-pack data model and Markdown renderer

**Files:**
- Create `apps/api/darknetra_api/reporting/model.py`.
- Create `apps/api/darknetra_api/reporting/markdown.py`.
- Create Jinja templates/tests.

**Interfaces:**
- Sections: cover/case metadata, scope/source classes, approved summary optional, evidence inventory/integrity, activity candidates, alias/clusters, link reasoning, graph snapshot reference, timeline, alerts, analyst decisions, methods/versions, limitations/contradictions, evidence appendix.

- [ ] **Step 1: Write report tests** ensuring only analyst-approved inferences appear in Findings; pending candidates appear in Unverified Leads.
- [ ] **Step 2: Every factual item carries evidence IDs** and every analytic item method/version.
- [ ] **Step 3: Redaction policy applied before template**; raw sensitive values absent from default report model.
- [ ] **Step 4: Markdown escapes imported content** so source text cannot inject active links/scripts/HTML.
- [ ] **Step 5: Commit** `feat: generate deterministic investigation markdown`.

---

### Task 11: Implement PDF rendering, output hashing, and report registry

**Files:**
- Create `apps/api/darknetra_api/reporting/pdf.py`.
- Add report models/migration/routes/tests.

**Interfaces:**
- `POST /api/v1/cases/{case_id}/reports` with format/sections/redaction profile.
- Generated Markdown/PDF saved through ObjectStore, SHA-256 hashed, registered with template/version/input snapshot digest.

- [ ] **Step 1: Write deterministic-content tests** for same report snapshot/template producing same Markdown bytes; PDF may contain renderer metadata so compare semantic/text + hash registration rather than promise byte identity unless configured deterministic.
- [ ] **Step 2: Configure WeasyPrint no remote network resources**; all CSS/assets bundled locally.
- [ ] **Step 3: Register report and audit generation/download**.
- [ ] **Step 4: Report cannot include active hyperlinks to operational source locators by default.
- [ ] **Step 5: Commit** `feat: register hashed investigation reports`.

---

### Task 12: Replace Reports UI shell

**Files:**
- Create `apps/web/src/features/reports/**`.

- [ ] **Step 1: Tests** for section selection, redaction profile, preview of pending-vs-approved distinctions, digest/template version display.
- [ ] **Step 2: Generate action waits for backend**; no fake instant report.
- [ ] **Step 3: Report history table** format, creator, timestamp, digest, template version, download permission.
- [ ] **Step 4: Commit** `feat: add investigator report generation UI`.

---

### Task 13: Optional local LLM draft-summary boundary

**Files:**
- Create only if core Tasks 1-12 pass: `apps/api/darknetra_api/llm/**`, model manifest, tests.

**Interfaces:**
- Output type `ANALYTIC_NOTE_DRAFT`; never report finding/evidence.

- [ ] **Step 1: Add explicit feature flag default false**.
- [ ] **Step 2: Context contains sanitized structured case facts and evidence IDs, not unrestricted raw files.
- [ ] **Step 3: Model has no tools, shell, network, collector or DB-write capabilities.
- [ ] **Step 4: Post-processor rejects citations to unknown evidence IDs and unsupported claims outside supplied structured context.
- [ ] **Step 5: Deterministic reports work with feature disabled.
- [ ] **Step 6: Commit separately** `feat: add optional grounded local analyst draft` so it can be reverted independently.

---

### Task 14: Trend/report evaluation and final Plan 06 verification

**Files:**
- Create `evaluation/trends/score.py` and planted synthetic time-series dataset.
- Create `docs/architecture/graph-trends-reports.md`.
- Create `docs/verification/plan-06-graph-trends-reports.md`.

- [ ] **Step 1: Evaluate planted trend recall, alert precision, false-positive rate, source-evidence trace completeness.
- [ ] **Step 2: Run projection parity test incremental vs rebuild.
- [ ] **Step 3: Delete/clear Neo4j in disposable environment and prove UI graph recovers after rebuild.
- [ ] **Step 4: Generate Markdown/PDF report and verify registered SHA-256/content access/audit.
- [ ] **Step 5: Run full suite/build/E2E/Compose smoke and record actual results/commit SHA.
- [ ] **Step 6: Commit** `docs: verify graph trends and reporting milestone`.

---

## Plan 06 Definition of Done

- Transactional outbox prevents request-time dual writes.
- Projector is idempotent and failure/retry does not mark unpublished rows as published.
- Full Neo4j rebuild matches incremental projection for authoritative graph content.
- Graph API is bounded and case-authorized; UI exposes provenance and accessibility alternative.
- Timeline is PostgreSQL-authoritative and timezone-explicit.
- Trends dedupe mirrors/repeats and require meaningful absolute/diversity thresholds.
- Alerts show baseline/current/source diversity/evidence and human disposition.
- Reports distinguish facts, analytic outputs, pending leads, analyst-confirmed findings, contradictions and limitations.
- Markdown/PDF outputs are safe, local-resource-only, hashed and registered.
- Core report generation works without an LLM.
- Full verification/evaluation is recorded.

## Plan 07 handoff contract

Plan 07 may rely on the complete core product workflow and must focus on reproducible synthetic/research data, measured evaluation, security/offline packaging, CI hardening, backup/restore and a deterministic hackathon demo. It must not add major new product scope.