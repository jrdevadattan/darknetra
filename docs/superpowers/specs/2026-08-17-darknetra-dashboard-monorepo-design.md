# DARKNETRA Monorepo and Investigator Dashboard Design

**Date:** 2026-08-17  
**Status:** Approved design, implementation not started  
**Target branch:** `testing-codex`

## 1. Product intent

DARKNETRA is an evidence-first, multilingual narcotics-intelligence and criminal-network discovery platform for authorized investigators.

The product must turn fragmented digital evidence into explainable investigative leads while retaining the provenance of every source artifact and every analytic result.

Core product statement:

> Existing OSINT tools can help find and summarize material. DARKNETRA preserves what was found, structures it, correlates identities, explains relationships, detects trends, and ties every conclusion back to evidence.

DARKNETRA is not a generic darknet search dashboard and not an LLM-first application.

## 2. Repository strategy

The repository is a monorepo.

```text
darknetra/
├── apps/
│   ├── web/                  # Next.js investigator dashboard
│   └── api/                  # FastAPI application
├── services/
│   ├── worker/               # Celery analysis jobs
│   ├── graph-projector/      # PostgreSQL outbox -> Neo4j projection
│   └── collector/            # optional lawful public-source collector
├── packages/
│   ├── ui/                   # shared UI primitives
│   ├── contracts/            # generated/shared API types and schemas
│   └── config/               # shared frontend/tooling configuration
├── models/
│   └── manifests/            # pinned local-model metadata/digests
├── infrastructure/
│   ├── docker/
│   └── nginx/
├── datasets/
│   └── synthetic/
├── scripts/
├── tests/
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── research/
│   └── superpowers/
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
├── Makefile
└── README.md
```

`main` remains stable. All initial product development happens on `testing-codex`.

## 3. Technical architecture

### Frontend

- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind CSS v4
- shadcn/Radix-style accessible primitives
- TanStack Query for server state
- Cytoscape.js for investigation graphs
- Recharts or ECharts for trend/time-series views

### Backend

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic migrations
- PostgreSQL + pgvector
- Redis + Celery
- Neo4j as a rebuildable read/query projection

### Evidence storage

The default evidence store is a local content-addressed filesystem behind an abstraction. MinIO/S3-compatible storage is optional.

### Deployment

Docker Compose is the required local/offline orchestration mechanism. Core investigation workflows must function without live internet after dependencies, images, and model assets are prepared.

## 4. Architectural invariants

1. PostgreSQL is authoritative for cases, evidence metadata, entities, candidates, analyst decisions, alerts, reports, audit events, and outbox state.
2. Neo4j is derived and rebuildable. Never dual-write PostgreSQL and Neo4j from a business transaction.
3. Redis contains transient cache/queue state only.
4. Original evidence is immutable after ingestion.
5. Every normalized, parsed, rendered, or extracted object is a derivative linked to its original evidence object.
6. Every graph relationship retains provenance back to supporting evidence IDs.
7. Model output is never evidence.
8. An LLM cannot directly create accepted graph relationships, identity conclusions, or final enforcement decisions.
9. Analysis workers receive no general outbound-network capability.
10. Only an optional, policy-controlled collector may join an egress/Tor network.
11. Core product operation and the final demo must not depend on Tor, public internet, GPU access, or a cloud LLM.

## 5. Admin-dashboard adaptation

The frontend visual foundation is the MIT-licensed project:

`arhamkhnz/next-shadcn-admin-dashboard`

We will reuse/adapt useful layout and component patterns rather than preserving the template as a demo suite.

### Keep/adapt

- responsive application shell;
- collapsible sidebar and header;
- theme infrastructure;
- table patterns;
- forms and validation presentation;
- dialogs, sheets, dropdowns, tabs, badges, skeletons and toasts;
- authentication screen patterns;
- role/permission interaction patterns;
- reusable accessible UI primitives;
- responsive navigation behavior.

### Remove

The final product must not carry unrelated showcase modules such as:

- ecommerce;
- CRM;
- finance;
- academy;
- generic calendar;
- generic mail;
- demo chat;
- demo analytics pages unrelated to investigation workflows;
- example dashboards that do not map to DARKNETRA use cases.

No dead links or placeholder navigation should remain after adaptation.

## 6. DARKNETRA navigation model

```text
DARKNETRA
├── Overview
├── Cases
│   ├── Case Overview
│   ├── Evidence
│   ├── Entities
│   ├── Activity Candidates
│   ├── Link Analysis
│   ├── NarcoGraph
│   ├── Timeline
│   ├── Alerts
│   └── Reports
├── Intelligence
│   ├── Emerging Trends
│   └── Source Registry
├── Administration
│   ├── Users
│   ├── Roles & Permissions
│   ├── Taxonomies
│   └── System Settings
├── Audit
└── System Health
```

Case-scoped routes should be nested under a case identifier so investigators always understand which investigation they are viewing.

Recommended route shape:

```text
/dashboard
/cases
/cases/[caseId]
/cases/[caseId]/evidence
/cases/[caseId]/entities
/cases/[caseId]/activity
/cases/[caseId]/links
/cases/[caseId]/graph
/cases/[caseId]/timeline
/cases/[caseId]/alerts
/cases/[caseId]/reports
/intelligence/trends
/intelligence/sources
/admin/users
/admin/roles
/admin/taxonomies
/admin/settings
/audit
/system/health
```

## 7. Primary screens

### Overview

Purpose: quick triage, not decorative analytics.

Show only actionable metrics such as active cases, evidence awaiting verification, link candidates awaiting analyst review, unresolved alerts, failed jobs, and evidence-integrity warnings.

Every metric must navigate to the relevant filtered work queue.

### Cases

Searchable, filterable, paginated case inventory with status, owner, sensitivity, evidence count, alerts, pending reviews, and recent activity.

### Case overview

Display evidence/entity/link/alert counts, integrity status, source-class composition, recent timeline, current analyst tasks, and prominent source-class badges such as `SYNTHETIC` and `RESEARCH_ARCHIVE`.

### Evidence

Inventory of original and derived artifacts. Show integrity, source class/type, timestamp, custody/lineage, restricted preview, and explicit re-verification actions.

### Entities

Structured entities including substance, alias, price, quantity, location, shipping term, contact, platform, wallet, PGP and image indicators. Values link to exact evidence spans.

### Activity candidates

Explainable transactional-drug-activity candidates with score decomposition, negative-context evidence, source references, and analyst disposition.

### Link analysis

Side-by-side alias/entity comparison with supporting and contradicting signals, image comparison, style summary, evidence drill-down, and accept/reject/defer actions with mandatory rationale.

### NarcoGraph

Case-scoped relationship graph with node/edge filters, accepted-versus-pending distinction, one-hop expansion by default, provenance drawer, and a keyboard-accessible tabular alternative.

### Timeline

Capture, observation, first-seen/last-seen, analytic job, analyst decision, and alert events. Preserve UTC while retaining original timezone metadata.

### Alerts / emerging trends

Deduplication-aware alerts with time series, source diversity, alias/cluster diversity, evidence drill-down, severity, status and disposition.

### Reports

Generate deterministic Markdown/PDF investigation packs with section selection, redaction preview, evidence references, template version and report digest.

### Administration

Users, roles, permissions, taxonomies, system settings, model configuration and source-registry policy. Actions must be role-aware and auditable.

### System health

Database, Redis, graph-projector, worker queue, evidence store and optional-model/collector status. Failures must be explicit rather than hidden behind generic green/red indicators.

## 8. UX rules

1. No decorative KPI cards without a workflow action.
2. Tables require useful filtering, sorting, pagination, loading, empty, partial and error states.
3. Destructive or high-impact actions require confirmation and authorization.
4. Restricted media is blurred by default with a warning before reveal.
5. No autoplay for evidence media.
6. Status is never conveyed using color alone.
7. Graph relationships must open their supporting evidence/provenance.
8. Desktop investigator workflows have priority, but navigation and review flows remain usable on tablet/mobile.
9. Use the epistemic labels `candidate`, `lead`, `pending analyst review`, `analyst-confirmed`, and `rejected`.
10. Do not automatically label a person or account `criminal`, `guilty`, or equivalent.
11. Full sensitive values are hidden/redacted by default; authorized reveal is audited.
12. The UI must distinguish observed facts, model outputs, analytic inferences, and human decisions.

## 9. Data flow

```text
Authorized import / replay / optional collector
              ↓
Evidence ingestion
  MIME/size/policy checks
  cryptographic digest
  immutable original
  provenance/custody manifest
              ↓
Safe derivatives
  text normalization
  image derivatives
  structured parsing
              ↓
Deterministic validators + NLP/image/style extractors
              ↓
Canonical entities in PostgreSQL
              ↓
Transactional drug-activity candidates
              ↓
Explainable alias/link candidate generation
              ↓
Human review and decision
              ↓
Transactional outbox
              ↓
Neo4j graph projection
              ↓
Trend aggregation / alerts / reports
```

## 10. Error handling expectations

Failures are domain states, not only logs.

The UI/API must explicitly represent:

- quarantined evidence;
- unsupported MIME/type;
- checksum mismatch;
- partially parsed artifact;
- extractor failure;
- stale analysis;
- background job retry/exhaustion;
- Neo4j projection lag/outage;
- Redis outage;
- source unavailable;
- authorization denied;
- redaction-required state;
- model unavailable;
- offline mode;
- optional collector disabled by policy.

No hash mismatch may silently replace the recorded expected digest.

No analytic failure may mutate or delete the original evidence artifact.

## 11. Security boundary

DARKNETRA must not:

- break or bypass end-to-end encryption;
- create or use criminal-market accounts;
- solve CAPTCHAs or bypass bot/access controls;
- contact sellers;
- purchase or facilitate purchase of controlled substances;
- execute evidence files or active content;
- deploy malware/exploits;
- claim that wallet ownership proves a natural-person identity;
- use stylometry as proof of identity;
- treat a drug keyword alone as proof of a sale;
- depend on a cloud LLM for core analysis.

All source material is treated as untrusted input, including prompt-injection text.

## 12. Testing strategy

Implementation will use TDD for independently testable behavior.

Required test layers:

- frontend unit/component tests;
- frontend accessibility tests for core flows;
- API unit tests;
- database integration tests;
- evidence-integrity/tamper tests;
- archive/MIME/path-traversal/size-limit tests;
- extractor tests with positive, negative and adversarial fixtures;
- alias-fusion hard-negative tests;
- graph projection/outbox idempotency tests;
- RBAC/cross-case authorization tests;
- end-to-end investigator workflow tests;
- Docker Compose smoke tests;
- offline/replay demo test;
- evaluation scripts for entity extraction, link precision/recall, false-link rate and alert precision.

No milestone is considered complete from code inspection alone; verification output is required.

## 13. Open-source attribution

Selected source/layout/component code may be adapted from `arhamkhnz/next-shadcn-admin-dashboard` under its MIT License. The original copyright and permission notice must be retained in `LICENSES/` and where legally required for substantial copied portions.

DARKNETRA-specific product logic, investigator workflows, evidence architecture, extraction/fusion logic, graph model, trend logic and reporting are separate project work.

## 14. Implementation sequencing

The implementation plan will be written only after this design is reviewed.

Planned order:

1. monorepo/tooling/Docker foundation;
2. frontend shell cleanup and DARKNETRA route/navigation scaffold;
3. backend health/config/database foundation;
4. authentication + case-scoped RBAC;
5. case lifecycle;
6. evidence vault and safe ingestion;
7. extraction and deterministic indicators;
8. activity-candidate scoring;
9. image/style correlation;
10. explainable link fusion + analyst decisions;
11. transactional outbox + Neo4j projection + graph UI;
12. timeline, trend alerts and reporting;
13. synthetic/replay evaluation and offline demo hardening;
14. optional lawful collector only after core stability and explicit policy enablement.

## 15. Success criteria

The product is successful when an authorized investigator can import a controlled evidence bundle, verify preserved originals, inspect structured multilingual entities, review an explainable cross-platform link candidate, open every supporting source artifact, accept/reject the candidate with an audit trail, explore the resulting graph/timeline, view a deduplicated trend alert, and export an evidence-linked report — all from a one-command Dockerized local deployment without relying on live Tor or a cloud LLM.
