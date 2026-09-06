# Plan 07 — Analytics: correlation, activity, graph, decisions, findings, wallets, trends

Milestone M4 · Owner C (analytics), A (decisions/findings) · Depends on 04, 06.

**Goal.** Explainable link candidates between aliases with per-signal contributions, transactional-activity candidates with negative-context safeguards, a materialised provenance graph, analyst decisions with side effects, findings with versions, wallet assessments (GraphSAGE + sanctions), and deduplicated trend series. Scores are engineering rankings, never probabilities of guilt.

**Architecture.** Deterministic, versioned services under `analytics/`; every run records its config digest; candidates are immutable per version; decisions are separate rows that change edge status. The GNN is called through the fixed `models/gnn/predict.py` contract on a subgraph assembled from the case ledger tables.

---

## Files

```
darknetra/analytics/
├── models.py            AnalyticRun, LinkCandidate, ActivityCandidate, WalletAssessment, TrendBucket, GraphEdge, LedgerNode, LedgerEdge, LedgerAddress
├── profiles.py          AliasProfile builder (evidence, fingerprints, contacts, wallets, image hashes, texts, timestamps, claims)
├── blocking.py          candidate_pairs(profiles) → set[(a,b)]
├── features/
│   ├── base.py          FeatureContribution(name, family, value, weight, contribution, evidence_ids, explanation)
│   ├── pgp.py contact.py wallet.py image.py stylometry.py rare_phrase.py temporal.py operational.py contradiction.py
├── link_scoring.py      score(profile_a, profile_b, config) → ScoredPair
├── correlate.py         run_case(case_id, focus?) → AnalyticRun (persists candidates, versions, edges)
├── activity.py          score_evidence(evidence_id) ; negative_context(text) → (penalty, cues)
├── graph.py             materialise(case_id); query(case_id, focus, depth, include_pending) → GraphDTO; provenance(edge_id)
├── gnn.py               GnnPredictor (loads models/gnn on first use; optional extra), assess(address) → GnnResult | None
├── sanctions.py         OfacList (offline JSON built by scripts/build_ofac_list.py); check(address) → SanctionsResult
├── wallets.py           assess_wallet(ctx, address, chain, live) → WalletAssessment (live part wired in plan 08)
├── trends.py            compute_buckets(case_id, window_days); candidates(case_id) → TrendCandidate[]
├── config.py            LinkConfig, ActivityConfig, TrendConfig (versioned, digest())
darknetra/decisions/
├── models.py            Decision, Finding
├── service.py           decide(...) with side effects; conflicts; findings create/promote/supersede
darknetra/tools/impl/analytics.py   correlate, graph, detect_trends, assess_wallet
darknetra/tools/impl/case.py        record_decision (fill), create_finding
darknetra/api/v1/routes/analytics.py findings.py (replace stubs)
backend/scripts/build_ofac_list.py  downloads SDN XML → data/sanctions/ofac_digital_currency.json (address, currency, program, entity)
alembic/versions/0007_analytics.py
tests/unit/analytics/test_profiles.py test_blocking.py test_features_*.py test_link_scoring.py test_activity.py test_graph.py test_gnn.py test_sanctions.py test_trends.py
tests/integration/test_correlate_synthetic.py test_decisions.py test_findings.py test_wallets.py test_graph_api.py test_trends_api.py
```

---

## Interfaces

### Alias profiles

An alias is a canonical entity of type `VENDOR_ALIAS` (listing vendor names, profile names) or a chat sender (`CONTACT_HANDLE` with `meta.role=sender`). Profile fields: `evidence_ids`, `fingerprints` (computed only), `contacts` (handles, emails, phones), `wallets` (with `tag` from `ledger_addresses` or inferred), `image_hashes` (pHash of images in the same evidence item or referenced by `media_refs`), `texts` (messages/descriptions authored by the alias), `timestamps`, `claims` (ship-from, locations from LOCATION observations within the alias's texts), `platforms`.

### Blocking

Pairs are considered only when at least one holds: shared fingerprint; shared contact; shared wallet; image family (any pHash distance ≤ 8); alias string similarity ≥ 85 (RapidFuzz `token_set_ratio` on casefolded, punctuation-stripped names); same platform and overlapping 30-day window with ≥ 2 shared lexicon terms. Never more than 5,000 pairs per run (largest cases truncate by strongest blocking key and log a warning).

### Features (weights from `LinkConfig`, version 1)

| Feature | Family | Value rule | Weight |
|---|---|---|---|
| `pgp_fingerprint` | CRYPTOGRAPHIC_IDENTIFIER | 1.0 if any computed fingerprint shared; 0 otherwise | 0.25 |
| `wallet_reuse` | CONTACT_CRYPTO | 1.0 if a shared wallet is `vendor_controlled`/`unknown`; **0 with reason `shared_service`** if tagged `shared_service` or seen on ≥ 3 aliases | 0.18 |
| `contact_reuse` | CONTACT_CRYPTO | 1.0 for a shared normalised handle/email/phone | 0.15 |
| `image_family` | IMAGE | 1 − (min pHash distance / 16) for distance ≤ 8; 0 above; suppressed to 0.2·value when the image family appears on ≥ 4 aliases (stock image) | 0.15 |
| `stylometry` | TEXT_STYLE | cosine of char 3–5-gram TF-IDF over the alias's texts after removing template-common sections (lines shared by ≥ 3 aliases); requires ≥ 300 chars and ≥ 2 documents per side, else `insufficient_evidence` (value 0, flagged) | 0.10 |
| `rare_phrase` | TEXT_STYLE | share of 4-gram phrases common to both with document frequency ≤ 2 across the case corpus | 0.07 |
| `temporal` | TEMPORAL_OPERATIONAL | overlap of active windows and a "migration" bonus when one alias stops within 7 days of the other starting | 0.05 |
| `operational` | TEMPORAL_OPERATIONAL | Jaccard of claimed ship-from/locations and price-per-unit similarity | 0.05 |
| `contradiction` | — | 1.0 when both aliases have different computed fingerprints in overlapping windows, or claim different ship-from cities in the same week; subtracts | 0.15 |

`score = round(100 · clip(Σ weight·value − 0.15·contradiction, 0, 1))`; bands `<40 WEAK`, `40–54 POSSIBLE`, `55–74 LEAD`, `≥75 STRONG`. Independence rule: STRONG requires ≥ 2 distinct families with contribution > 0 and at least one of `pgp_fingerprint`, context-consistent `wallet_reuse`, `contact_reuse`, or `image_family`; otherwise the band is capped at LEAD with `meta.capped_by="independence_rule"`.

### Candidates and versions

`link_candidates` unique on `(case_id, subject_a_id, subject_b_id, version)` with `a < b` ordering. A new run computes a new `version` only when the feature vector changed (digest of contributions and evidence ids); unchanged pairs keep their version and decision. Changed pairs get `version+1`, `supersedes_id`, status PENDING, and `meta.rescored=true`; the previous decision stays attached to the old version (scenario 16).

### Activity scoring (per listing evidence or per message cluster of 5 consecutive messages by one sender)

`score = 0.45·substance + 0.15·quantity + 0.10·price_payment + 0.10·shipping + 0.10·contact_crypto + 0.10·listing_context − penalty`, each feature ∈ [0,1] from observation confidences in the span; labels `< 0.35 LOW_SIGNAL`, `0.35–0.65 CANDIDATE`, `> 0.65 HIGH_PRIORITY_REVIEW`. Negative-context cues (English, Hindi, Punjabi): `seized, seizure, arrested, police, NCB, court, judgment, study, research, hospital, prescription, overdose awareness, news, reported, जब्त, गिरफ्तार, पुलिस, अदालत, ਜ਼ਬਤ, ਪੁਲਿਸ`; offer cues: `available, dm, price, delivery, order, milega, bhej, cod, stock`. Penalty 0.5 when ≥ 2 negative cues and no offer cue; 0.25 when negative cues ≥ offer cues.

### Graph

Nodes: canonical entities (+ evidence nodes when `include_evidence`). Edge types: `CO_OCCURS` (entities in the same evidence; provenance = evidence ids), `USES` (alias → wallet/contact/fingerprint from the alias's evidence), `POSSIBLE_SAME_OPERATOR` (link candidate; `status` from candidate; score, families), `ANALYST_CONFIRMED_RELATED` (created on ACCEPT), `MENTIONS_LOCATION`, `CONTAINS` (evidence → child). `materialise(case_id)` rebuilds `graph_edges` idempotently from observations and candidates. DTO: BFS from `focus` (entity id) to `depth ≤ 2`, node cap 500, edge cap 2,000; pending edges dashed (`status=PENDING`), rejected hidden unless `include_rejected`. `provenance(edge_id)` returns evidence codes, candidate id, decision id, feature table.

### Decisions

```python
async def decide(session, *, case, actor, target_type, target_id, decision, rationale, supersede=False) -> Decision
```

Rules: rationale required for ACCEPT/REJECT (≥ 10 chars); existing decision on the same target and version → 409 `CONFLICT` with the existing decision in `detail`, unless `supersede=true` and actor has LEAD/OWNER (new decision row, old kept with `superseded_by`). Side effects in the same transaction: LINK ACCEPT → edge `ANALYST_CONFIRMED_RELATED` + candidate ACCEPTED; REJECT → candidate REJECTED, edge hidden; DEFER → PENDING with `deferred_at`; ALERT ACCEPT/ESCALATE → handled in plan 09; FINDING ACCEPT → finding `kind=CONFIRMED`. Audit `decision.<type>` with `result_hash`.

### Findings

`create(case, thread_id?, title, claim, evidence_codes, method, method_version, kind_hint)` → DRAFT; `promote(finding_id, decision_id)` → PROMOTED with `kind` per decision; `supersede(finding_id, new_claim)` → new version. Findings created from a claim record `source_message_id` and `claim_index`.

### Wallets

```python
class GnnPredictor:
    available: bool                                  # torch + torch_geometric importable and models/gnn present
    def assess(self, case_id, address) -> GnnResult | None   # None with reason when address ∉ ledger_addresses
```
Subgraph: `ledger_addresses(address → node_index)` → 2-hop neighbourhood over `ledger_edges` (cap 2,000 nodes) → `features (N,102)` from `ledger_nodes` → `predict(features, edge_index, node_index)` → `{prediction, class, illicit_probability, licit_probability, threshold, model_version, n_nodes, caveat:"research model; illicit-class F1 0.58"}`. Never alter the threshold.

Sanctions: `OfacList.check(address)` → `{sanctioned: bool, program, entity, list_version, source:"ofac_sdn_offline"}`; Chainalysis live check added in plan 08 with `source:"chainalysis_live"`.

`assess_wallet(ctx, address, chain, live)` → persists `wallet_assessments` and returns `{address, chain, gnn, sanctions, live_summary (plan 08), tags (from ledger_addresses / observations), assessed_at, version}`; Monero → `{traceable:false, reason}`.

### Trends

`compute_buckets(case_id, window_days=30)`: for each lexicon term and each `SLANG_CANDIDATE`/alias/wallet entity, per UTC day: `count`, `unique_evidence_families` (near-duplicate captures collapsed by content hash and pHash), `unique_aliases` (senders/vendors), `unique_sources` (source class + domain/channel). `candidates()`: z-score `(x_t − mean_{t−14..t−1}) / max(std, 1)`; candidate when `z ≥ 3`, `count ≥ 3`, `unique_sources + unique_aliases ≥ 3`; series returned for the panel; plan 09 turns candidates into `TREND` alerts.

### Tools registered

`correlate {focus_entity_id?}` → `{run_id, candidates:[…top 20 by score with features], version_changes}`; `graph {focus, depth, include_pending}` → DTO; `detect_trends {window_days}` → `{series, candidates}`; `assess_wallet {address, chain?, live?}`; `record_decision {target_type, target_id, decision, rationale}`; `create_finding {...}`. All `CASE_LEAD` only except `assess_wallet` (also CHAIN_ANALYST) and `graph` (also REPORTER).

### Endpoints (replace stubs)

`POST /analytics/correlate`, `GET /analytics/links[/{id}]`, `GET /analytics/activity`, `GET /graph`, `GET /graph/edges/{id}/provenance`, `POST /wallets/assess`, `GET /wallets`, `GET /trends`, `POST /decisions`, `GET /decisions`, `POST/GET /findings`, `POST /findings/{id}/promote`, `POST /threads/{tid}/pin`.

---

## Tasks

- [ ] **T1 migration 0007 + models** (incl. ledger tables loaded by the seed from `ledger/*.csv` via `POST /cases/{id}/ledger/import` — add this endpoint here, ADMIN or LEAD).
- [ ] **T2 profiles + blocking** with unit tests (no all-pairs explosion; planted pair not blocked out).
- [ ] **T3 features**: one test module per feature with synthetic profiles; template discount; stock-image suppression; shared-service zeroing; contradiction.
- [ ] **T4 scoring + bands + independence rule + versioning**; exact arithmetic tests; scenario 14, 15, 16.
- [ ] **T5 activity + negative context** (scenario 13).
- [ ] **T6 graph materialise/query/provenance** with cardinality tests.
- [ ] **T7 decisions + findings** with conflict, supersede, side effects (scenario 17).
- [ ] **T8 gnn + sanctions + assess_wallet**: GNN test uses a tiny fake model when torch is absent (`GnnPredictor.available=False` path, scenario 38); OFAC list builder with a fixture XML; scenario 37, 39.
- [ ] **T9 trends** with planted series tests (spike with diversity alerts; single-sender spam does not).
- [ ] **T10 tools + endpoints**.

## Acceptance gate

On SYN-CHD-001: `correlate` yields the planted pair STRONG (≥ 75) with families {CRYPTOGRAPHIC_IDENTIFIER, IMAGE, CONTACT_CRYPTO}, the decoy pair WEAK (< 40) with `wallet_reuse` explanation `shared_service`; ACCEPT creates the confirmed edge visible in `/graph`; `assess_wallet` for W1 returns `gnn.class=1` (dataset path) or `gnn=null` with reason (fallback path) and a sanctions result; trend candidate `safed line` appears, `purani cheez` does not.

## Handoff

Plan 08 adds the live chain summary and sanctions to `assess_wallet`; plan 09 consumes trend candidates and decisions on alerts; plan 10 renders candidates, decisions and wallets into the pack.
