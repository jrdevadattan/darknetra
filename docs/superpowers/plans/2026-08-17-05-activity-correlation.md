# DARKNETRA Transactional Activity and Explainable Correlation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn extracted observations into explainable transactional-drug-activity candidates and conservative cross-platform alias-link candidates using independent evidence families, hard-negative safeguards, and mandatory analyst decisions.

**Architecture:** Activity scoring and identity-correlation are deterministic/versioned analytic services whose inputs are evidence-linked observations and feature records. Image and stylometric features are stored as derived analytic artifacts; link scores expose every positive and contradictory contribution. Candidates never become accepted relationships automatically: analyst acceptance/rejection/defer is a separate audited human decision.

**Tech Stack:** FastAPI/SQLAlchemy/PostgreSQL, Celery, scikit-learn, character n-gram TF-IDF, Pillow/ImageHash pHash/crop-resistant hash, optional local DINOv2-small embeddings behind a pinned model manifest, pgvector for embeddings when useful, NumPy, pytest/Hypothesis, React, TanStack Query.

## Global Constraints

- Begin only after Plan 04 verification.
- A drug/substance mention alone MUST NOT be labelled a sale.
- Activity/link scores are engineering ranking scores, not calibrated probabilities of criminality or identity.
- Strong alias links require at least two independent signal families and may not be strong from stylometry alone.
- Same marketplace escrow/shared-service wallet must not by itself link vendors.
- Same stock/common image must not by itself create a strong link.
- Copy-pasted marketplace templates must not inflate stylometry/rare-phrase signals.
- PGP fingerprint, validated contact reuse, context-consistent wallet reuse, and near-duplicate image may be strong evidence but remain investigative indicators.
- Every candidate stores model/rule version, feature decomposition, supporting evidence IDs, contradictions, and analyst state.
- Human actions: `ACCEPT`, `REJECT`, `DEFER`, `REQUEST_MORE_EVIDENCE`; rationale required for accept/reject.
- Accepted relationship is still an analyst-confirmed investigative relationship, not proof of a natural person's identity or guilt.

---

## Activity score contract

Use configurable engineering weights initialized as:

```text
ActivityScore =
  0.45 * substance_confidence
+ 0.15 * quantity_evidence
+ 0.10 * price_payment_evidence
+ 0.10 * shipping_evidence
+ 0.10 * contact_crypto_evidence
+ 0.10 * vendor_listing_context
- negative_context_penalty
```

Feature values are clamped to `[0,1]`; final score is clamped `[0,1]`. Threshold defaults are versioned configuration, not hard-coded UI truth.

Negative contexts include news/reporting, academic/research discussion, policy/legal text, medical/pharmaceutical safety discussion, and seizure reporting when no sale/offer context exists.

---

## Alias-link score contract

Initial engineering score:

```text
LinkScore = 100 * clip(
  0.25*PGP
+ 0.18*Wallet
+ 0.15*Contact
+ 0.15*Image
+ 0.10*Stylometry
+ 0.07*RarePhrase
+ 0.05*Temporal
+ 0.05*Operational
- 0.15*Contradiction,
0, 1)
```

Confidence bands:

```text
<40     Weak similarity; hidden by default
40-54   Possible relationship; analyst inspection
55-74   Investigative lead
>=75    Strong candidate link; analyst verification required
```

A score >=75 is invalid unless at least two independent signal families contribute and at least one normally comes from PGP, validated contact/context-consistent crypto reuse, or image evidence.

---

### Task 1: Add activity/link feature, candidate, decision, and model-version schema

**Files:**
- Create `apps/api/darknetra_api/models/analytics.py`.
- Create schemas/migration/tests.

**Interfaces:**
- Tables: `analytic_runs`, `activity_candidates`, `activity_features`, `alias_link_candidates`, `alias_link_features`, `analyst_decisions`, `image_features`, `style_profiles`.

- [ ] **Step 1: Write failing constraints tests** for score bounds, version presence, evidence reference, candidate status, decision rationale, immutable feature snapshots after candidate creation.
- [ ] **Step 2: Implement models** so candidate row references a specific analytic run/config digest; feature rows include name, normalized value, weighted contribution, explanation, evidence IDs.
- [ ] **Step 3: Add uniqueness/idempotency** by `(candidate_subjects, analytic_run_version/input_digest)`.
- [ ] **Step 4: Generate/apply migration and commit** `feat: define explainable analytic candidate schema`.

---

### Task 2: Implement transactional activity feature extraction and negative-context safeguards

**Files:**
- Create `apps/api/darknetra_api/analytics/activity_features.py`.
- Create tests.

**Interfaces:**
- `build_activity_features(observation_bundle) -> ActivityFeatureSet`.

- [ ] **Step 1: Write positive synthetic tests** combining substance + quantity + price/shipping/contact/vendor-listing context.
- [ ] **Step 2: Write hard negatives**: newspaper seizure article, academic paper, harm-reduction guidance, prescription information, legal judgment, casual non-commercial mention.
- [ ] **Step 3: Implement feature values** from evidence-linked entities/context only; no LLM judgement.
- [ ] **Step 4: Implement negative-context classifier** as explainable rules + local text classifier only if measured improvement exists; rules/version are stored.
- [ ] **Step 5: Assert negative cases stay below transactional review threshold** on curated hard negatives before tuning positives.
- [ ] **Step 6: Commit** `feat: extract transactional activity signals`.

---

### Task 3: Implement versioned activity score service and analyst disposition

**Files:**
- Create `apps/api/darknetra_api/analytics/activity_scoring.py`.
- Create service/routes/tests.

**Interfaces:**
- `score_activity(features, config) -> ScoredActivityCandidate`.
- API list/detail/decision endpoints under `/cases/{case_id}/activity-candidates`.

- [ ] **Step 1: Write exact arithmetic tests** for each feature contribution, clamp, negative penalty, config version/digest.
- [ ] **Step 2: Implement threshold labels** `LOW_SIGNAL`, `CANDIDATE`, `HIGH_PRIORITY_REVIEW`; avoid `criminal`/`illegal seller` labels.
- [ ] **Step 3: Implement case API** with evidence drilldown and human disposition.
- [ ] **Step 4: Decision transaction appends audit event** and never changes original score/features; rescoring creates new version.
- [ ] **Step 5: Commit** `feat: rank explainable transactional activity candidates`.

---

### Task 4: Implement exact/near-duplicate image feature pipeline

**Files:**
- Create `apps/api/darknetra_api/analytics/images.py`.
- Create image feature worker/tests.

**Interfaces:**
- Exact SHA-256 identity; pHash/crop-resistant hash distances; optional DINO embedding and cosine similarity.

- [ ] **Step 1: Build generated image test set**: original, JPEG compression, resize, small/large crop, watermark, brightness, minor rotation, similar-but-different synthetic object, unrelated image.
- [ ] **Step 2: Implement SHA-256/pHash/crop-resistant hash** and feature versioning.
- [ ] **Step 3: Add DINOv2-small only behind local manifest**; if model absent, pHash pipeline remains fully functional and candidate records state `embedding_unavailable` rather than failing.
- [ ] **Step 4: Calibrate duplicate-family thresholds on generated test set** and store threshold config/version; do not claim published optimal values.
- [ ] **Step 5: Add common/stock-image suppression**: high-frequency image family across many unrelated aliases/sources reduces identity contribution.
- [ ] **Step 6: Commit** `feat: add evidence linked image correlation`.

---

### Task 5: Implement bounded stylometry profile

**Files:**
- Create `apps/api/darknetra_api/analytics/stylometry.py`.
- Create tests.

**Interfaces:**
- Account/alias style profile includes char 3-5 gram TF-IDF representation, punctuation/capitalization/length/function-word/error/emoji summary; only texts attributed to alias and passing minimum-quality filter contribute.

- [ ] **Step 1: Write tests** for same synthetic author across spelling noise, different authors, tiny samples, copied template, quoted text, duplicate listing descriptions.
- [ ] **Step 2: Set minimum evidence gate** by combined character count and minimum distinct documents; below it output `insufficient_evidence`, not similarity score.
- [ ] **Step 3: Remove/discount template-common sections** discovered across many aliases before style vector.
- [ ] **Step 4: Compute cosine similarity and bounded feature contribution**; store summary/explanation, not huge raw vector in API response.
- [ ] **Step 5: Ensure stylometry alone can never satisfy strong-link invariant** in integration tests.
- [ ] **Step 6: Commit** `feat: add bounded vendor stylometry signal`.

---

### Task 6: Implement rare-phrase, temporal, operational, PGP/contact/wallet signal builders

**Files:**
- Create `apps/api/darknetra_api/analytics/link_features.py`.
- Create tests.

**Interfaces:**
- `build_link_features(alias_a, alias_b, case_id) -> AliasLinkFeatureSet`.

- [ ] **Step 1: PGP signal** exact computed fingerprint match; contradiction when stable incompatible fingerprint history materially overlaps, with careful multi-key support.
- [ ] **Step 2: Contact signal** exact normalized contact reuse, role/context aware.
- [ ] **Step 3: Wallet signal** same validated address contributes only when context indicates vendor-controlled payment/contact indicator; known marketplace/shared escrow context contributes zero and records shared-service reason.
- [ ] **Step 4: Rare phrase** use corpus document frequency; phrase common across marketplace templates gets zero/suppressed contribution.
- [ ] **Step 5: Temporal** compare posting/activity windows and migration sequences; timezone normalization uses captured metadata, never guessed geography.
- [ ] **Step 6: Operational** shipping claims, claimed location, inventory/price patterns as low-weight supporting signal.
- [ ] **Step 7: Write contradiction tests** for mutually exclusive claims/time overlap/shared services and commit `feat: build cross alias correlation signals`.

---

### Task 7: Implement candidate blocking and explainable alias fusion

**Files:**
- Create `apps/api/darknetra_api/analytics/link_scoring.py`.
- Create job/service/tests.

**Interfaces:**
- Candidate pairs are generated only after broad blocking: shared PGP/contact/wallet/image family, semantic alias similarity, language/style neighborhood, overlapping market/category/time window.

- [ ] **Step 1: Write blocking tests** ensuring unrelated all-pairs explosion is avoided and known planted pairs are not blocked out.
- [ ] **Step 2: Write arithmetic tests** for exact weight/contribution decomposition and contradiction subtraction.
- [ ] **Step 3: Implement independence guard**: group signals by `CRYPTOGRAPHIC_IDENTIFIER`, `CONTACT_CRYPTO`, `IMAGE`, `TEXT_STYLE`, `TEMPORAL_OPERATIONAL`; >=75 needs >=2 groups and one strong family condition.
- [ ] **Step 4: Persist candidate explanation** as per-feature contributions with evidence IDs and model/config version.
- [ ] **Step 5: Re-score creates new candidate version or run linkage**; never rewrite historical analytic run.
- [ ] **Step 6: Commit** `feat: generate explainable alias link candidates`.

---

### Task 8: Implement analyst decision workflow and cluster consistency rules

**Files:**
- Create service/routes/tests for link decisions and vendor clusters.

**Interfaces:**
- API `/cases/{case_id}/link-candidates`, `/link-candidates/{id}/decision`.
- Vendor cluster creation only after accepted decision.

- [ ] **Step 1: Write tests** for accept/reject/defer/request-more-evidence, mandatory rationale, reviewer role permissions, repeated decision history.
- [ ] **Step 2: Accepted candidate creates/updates a vendor cluster through transaction** while preserving candidate and decision record.
- [ ] **Step 3: Implement cluster contradiction check** preventing silent merge if accepted clusters contain explicit incompatible analyst-confirmed relationships; return conflict requiring review.
- [ ] **Step 4: Rejection suppresses same analytic candidate version but allows new evidence/version to generate a new candidate linked to prior rejection context.
- [ ] **Step 5: Every decision audit includes candidate ID and evidence IDs, not sensitive full values.
- [ ] **Step 6: Commit** `feat: add analyst controlled identity correlation decisions`.

---

### Task 9: Replace Activity Candidates UI shell

**Files:**
- Create `apps/web/src/features/activity/**` and route tests.

- [ ] **Step 1: Component tests** verify score decomposition, negative context, evidence links, method/version, decision states, no probability/guilt wording.
- [ ] **Step 2: Implement list filters** status/score band/substance/source/decision.
- [ ] **Step 3: Implement detail panel** with positive/negative contributions and source snippets.
- [ ] **Step 4: Implement decision form** with rationale rules and optimistic UI disabled for decisions; wait for authoritative response.
- [ ] **Step 5: Commit** `feat: add transactional activity review UI`.

---

### Task 10: Replace Link Analysis UI shell with side-by-side evidence review

**Files:**
- Create `apps/web/src/features/links/**` and E2E tests.

- [ ] **Step 1: Write tests** for candidate bands, contribution/contradiction labels, required evidence list, status wording.
- [ ] **Step 2: Implement alias side-by-side summary** with source counts, markets, first/last seen and redacted indicators.
- [ ] **Step 3: Implement clickable contribution rows** opening exact supporting evidence contexts.
- [ ] **Step 4: Implement image comparison** original vs transformed safe preview with slider/toggle and method values; restricted media remains blurred until reveal.
- [ ] **Step 5: Implement style summary** showing evidence sufficiency and feature summary, never exposing it as sole proof.
- [ ] **Step 6: Implement accept/reject/defer/request-more-evidence with rationale/audit result.
- [ ] **Step 7: E2E** review a synthetic candidate, inspect PGP/image evidence, accept, observe analyst-confirmed cluster state.
- [ ] **Step 8: Commit** `feat: add explainable alias review experience`.

---

### Task 11: Add hard-negative correlation dataset and evaluation/ablation harness

**Files:**
- Create `datasets/synthetic/correlation/**` generator and ground-truth schema.
- Create `evaluation/correlation/score.py`.
- Create tests.

**Interfaces:**
- Hidden ground truth actor-to-alias mapping is never read by correlation service; scorer reads predictions separately.

- [ ] **Step 1: Generate at least these hard negatives**: shared marketplace escrow wallet, common stock image, copy-paste listing template, similar username unrelated actor, same language/timezone, marketplace announcement content.
- [ ] **Step 2: Generate positive challenges**: wallet changed but PGP/image retained; cropped image; code-mixed style shift; platform migration; one contradictory weak signal.
- [ ] **Step 3: Implement metrics** link precision, recall, high-confidence false-link rate, reason-trace completeness, strong-links-with-2-families percentage.
- [ ] **Step 4: Implement ablations** stylometry only; hard identifiers only; image+style; full fusion.
- [ ] **Step 5: Project target labels remain targets until measured**; report actual values only after run.
- [ ] **Step 6: Commit** `test: add alias correlation hard negative evaluation`.

---

### Task 12: Final Plan 05 verification/documentation

**Files:**
- Create `docs/architecture/activity-correlation.md`.
- Create `docs/verification/plan-05-activity-correlation.md`.

- [ ] **Step 1: Document score formulas/threshold config, feature independence, negative contexts, image/style limits, analyst decision semantics.
- [ ] **Step 2: Run full tests/build/E2E and evaluation scripts.
- [ ] **Step 3: Record actual activity/link metrics, false-link cases, model/config digests and commit SHA.
- [ ] **Step 4: Commit** `docs: verify activity and correlation milestone`.

---

## Plan 05 Definition of Done

- Transactional activity candidates require substance plus commercial/operational context and negative-context protection.
- Scores expose deterministic feature decomposition and version.
- Image pipeline distinguishes exact SHA, near-duplicate hash and optional embedding semantics.
- Stylometry has minimum-data/template safeguards and cannot create strong links alone.
- Shared wallets/stock images/templates have explicit hard-negative tests.
- Link >=75 invariant enforces multiple independent signal families.
- Analyst decision is required before cluster relationship becomes analyst-confirmed.
- Every feature/candidate/decision links to evidence and audit history.
- Activity and Link Analysis UIs make uncertainty and contradictions obvious.
- Evaluation reports measured precision/recall/false-link rate and ablations.

## Plan 06 handoff contract

Plan 06 may project accepted clusters, evidence-linked entities, pending/accepted link candidates, activity candidates and alerts into Neo4j as derived read state. PostgreSQL remains authoritative and the projector must be rebuildable/idempotent.