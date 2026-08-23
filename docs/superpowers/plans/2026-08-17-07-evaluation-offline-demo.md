# DARKNETRA Evaluation, Security, Offline Packaging, and Finale Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove DARKNETRA's core claims with a reproducible ground-truth dataset, hard-negative evaluations, security checks, backup/restore verification, offline Docker packaging, and a deterministic five-minute investigator demo that does not depend on live criminal infrastructure.

**Architecture:** A dataset generator creates fictional operators, aliases, listings/chat exports, images, test-only public PGP keys, local/test-network-style crypto indicators, multilingual text, planted trends, and deliberate false-link traps. Evaluation runs outside the production inference path and scores project outputs against hidden ground truth. Release packaging locks dependencies/images/models, generates SBOM/security reports, verifies restore/offline startup, and ships a replay bundle that exercises the same ingestion/analysis pipeline as real authorized evidence.

**Tech Stack:** Python, pytest, NumPy/pandas only if already justified for evaluation, Docker Compose, Syft, Trivy, Semgrep, Bandit, Ruff, mypy if configured, pnpm/TypeScript checks, Playwright, GitHub Actions, local model manifests.

## Global Constraints

- Begin only after Plans 01-06 verification.
- Synthetic data must be unmistakably labelled `SYNTHETIC`; historical research datasets must be `RESEARCH_ARCHIVE` with provenance/license notes.
- Never include operational onion locators, seller contact details, real private keys, unredacted personal data, or instructions for purchasing drugs.
- Hidden actor ground truth is accessible to evaluation scripts only; production correlation code must not read it.
- Published paper metrics are context, not DARKNETRA results. Report only metrics produced by this repository's scripts.
- Precision is prioritized over recall for alias linking because false linkage is operationally costly.
- Finale demo must work with network disabled after images/dependencies/model assets are prepared.
- Live Tor is optional and excluded from the required demo path.
- All release container/model/dependency versions are locked and recorded.

---

## Dataset target

Generate approximately:

```text
12 fictional ground-truth operators
24-30 vendor/chat aliases
120-150 marketplace-style listings
150-250 chat messages
80-100 benign/negative records
20-25 source images + 60-80 transformed variants
30-40 synthetic/local/test-format crypto indicator observations
8-12 test-only OpenPGP public identities
100+ multilingual/code-mixed passages
3-4 platform migration events
4-6 planted trends
10+ deliberate false-link traps
```

Exact counts may vary slightly through deterministic generation, but generator seed/config and actual counts must be written into dataset manifest.

---

### Task 1: Build deterministic synthetic ground-truth generator

**Files:**
- Create `datasets/synthetic/generator/**`.
- Create `datasets/synthetic/config.yaml`.
- Create `datasets/synthetic/schema/*.json`.
- Create tests.

**Interfaces:**
- CLI: `uv run python -m datasets.synthetic.generator --seed 20260817 --output .generated/synthetic-demo`.
- Output contains public replay bundle plus separate `ground_truth.json` used only by evaluation.

- [ ] **Step 1: Write determinism test**: same seed/config yields byte-identical JSON/text manifests and same artifact hashes; image encoder metadata may require deterministic settings.
- [ ] **Step 2: Define fictional operators** with alias sets, test PGP fingerprint IDs, synthetic wallet-cluster IDs, image-family IDs, style profile and timeline; no real identities.
- [ ] **Step 3: Generate listing/chat text** across English, Hindi, Punjabi, Hinglish/Romanized variants with transactional positives and benign negatives. Avoid operational market addresses or procurement instructions.
- [ ] **Step 4: Generate source images programmatically** using shapes/textures/labels, then deterministic transforms; do not scrape real product imagery.
- [ ] **Step 5: Generate ephemeral/test-only public PGP data** during generation and store public material only; private material is deleted after deriving fixtures.
- [ ] **Step 6: Generate format-valid test/synthetic crypto observations** from library test vectors/local fixtures where licensing permits; label them non-operational and never imply ownership.
- [ ] **Step 7: Write manifest** seed, generator commit/version, counts, language slices, trap/trend IDs, licenses/provenance.
- [ ] **Step 8: Commit generator/config/schema, not bulky generated output unless intentionally versioned and reviewed** with `feat: add deterministic synthetic investigation generator`.

---

### Task 2: Encode deliberate hard-negative and migration scenarios

**Files:** generator scenario modules/tests.

- [ ] **Step 1: Shared escrow trap** two unrelated aliases share marketplace-level payment indicator; expected no strong link from wallet.
- [ ] **Step 2: Stock/common-image trap** unrelated aliases use same generic image family; frequency suppression prevents strong link.
- [ ] **Step 3: Copy-paste template trap** unrelated aliases reuse marketplace boilerplate; stylometry/rare phrase suppression.
- [ ] **Step 4: Changed-wallet migration positive** same operator changes wallet but retains PGP/cropped image/style evidence.
- [ ] **Step 5: Cross-script positive** one alias uses native Hindi/Punjabi and another Romanized text; canonical entity relationship surfaces without claiming authorship from transliteration alone.
- [ ] **Step 6: Contradiction case** planted strong-looking shared image plus explicit incompatible hard identifier/time evidence; score records contradiction and does not blindly merge.
- [ ] **Step 7: Tamper case** copy of replay object plus test harness that modifies one byte after ingestion; original committed fixture stays unchanged.
- [ ] **Step 8: Commit** `test: add correlation and integrity hard negatives`.

---

### Task 3: Build end-to-end replay importer and golden scenario

**Files:**
- Create `scripts/load_demo_case.py`.
- Create E2E tests.

**Interfaces:**
- `uv run python scripts/load_demo_case.py --bundle <path> --case-code SYN-DEMO-001` uses public product APIs/service boundaries; no direct DB inserts except initial isolated admin fixture if explicitly test-only.

- [ ] **Step 1: Write replay-idempotency test** importing same bundle twice does not duplicate evidence; second run returns existing object/case references or explicit duplicate result.
- [ ] **Step 2: Import WARC/HTML/chat/image/indicator samples** through Evidence Vault pipeline and wait for jobs with bounded timeout.
- [ ] **Step 3: Golden scenario asserts** preserved hashes -> extracted entities -> activity candidate -> alias candidate -> analyst decision fixture action -> graph cluster -> planted alert -> report.
- [ ] **Step 4: Loader logs IDs/status only**, no sensitive content dump.
- [ ] **Step 5: Commit** `feat: add deterministic investigation replay loader`.

---

### Task 4: Unify extraction/activity/correlation/trend evaluation runner

**Files:**
- Create `evaluation/run_all.py`.
- Create result schema and tests.

**Interfaces:**
- CLI produces `evaluation-results.json` and `evaluation-results.md` with commit SHA/config/model manifests/dataset manifest hash.

- [ ] **Step 1: Call existing Plan 04/05/06 scorers** rather than reimplement metrics.
- [ ] **Step 2: Report extraction precision/recall/F1 by entity and language slice.
- [ ] **Step 3: Report image pair precision/recall, Recall@5 and unrelated false-match rate.
- [ ] **Step 4: Report alias link precision/recall/high-confidence false-link rate/reason-trace coverage/independent-family invariant.
- [ ] **Step 5: Report trend recall/precision/false-positive rate/evidence trace coverage.
- [ ] **Step 6: Report integrity experiment pass/fail and report-generation checks.
- [ ] **Step 7: Add ablation results** style-only, hard identifiers, image+style, full fusion.
- [ ] **Step 8: Never convert targets to achieved values**; output `measured` and optional `target` as distinct fields.
- [ ] **Step 9: Commit** `test: unify DARKNETRA evaluation reporting`.

---

### Task 5: Add performance budgets and representative load tests

**Files:**
- Create `evaluation/performance/**`.

**Interfaces:** non-production load harness.

- [ ] **Step 1: Define hackathon-scale budgets** in config, clearly engineering targets: dashboard API p95 under local controlled load, evidence list pagination, graph response bounded node count, typical evidence parse/job duration, report generation.
- [ ] **Step 2: Generate representative case** near synthetic target counts rather than internet-scale claims.
- [ ] **Step 3: Measure memory/time for 100 MiB streaming upload without reading whole file in RAM.
- [ ] **Step 4: Measure graph query depth/cardinality guard.
- [ ] **Step 5: Record actual environment hardware/versions with results.
- [ ] **Step 6: Commit** `test: add hackathon scale performance checks`.

---

### Task 6: Add static/security/dependency/SBOM gates

**Files:**
- Modify CI.
- Create `scripts/security_check.sh`.
- Create `docs/security/tooling.md`.

**Interfaces:**
- Commands: Ruff, Bandit, Semgrep, frontend lint/type/tests, dependency audit where reliable, Trivy images/filesystem, Syft SBOM.

- [ ] **Step 1: Add Bandit/Semgrep configurations** tuned to Python/FastAPI and frontend; suppressions require inline rationale or config comment.
- [ ] **Step 2: Add secret scan using available CI scanner**; repository fixtures must remain synthetic.
- [ ] **Step 3: Build images then run Trivy** for critical/high findings; allowlist only with issue/expiry/rationale.
- [ ] **Step 4: Generate Syft CycloneDX/SPDX SBOM artifacts** for release images/repository.
- [ ] **Step 5: Frontend dependency audit** is advisory for ecosystem false positives unless exploitable path is confirmed; critical exploitable findings block release.
- [ ] **Step 6: Commit** `ci: add security and SBOM release gates`.

---

### Task 7: Pin container images, Python/Node locks, and local model manifests

**Files:**
- Modify Dockerfiles/Compose.
- Verify `pnpm-lock.yaml`, `uv.lock`, model manifests.
- Create `release/manifest.schema.json`, `scripts/build_release_manifest.py`.

- [ ] **Step 1: Resolve immutable image digests** for Node/Python/Postgres/Redis/Neo4j and any renderer/model service used; replace floating release tags in release Compose/Dockerfiles with digest references while retaining human-readable comments/docs.
- [ ] **Step 2: Verify frozen installs** `pnpm install --frozen-lockfile`, `uv sync --frozen --all-packages`.
- [ ] **Step 3: Verify model files** exist locally and match manifest SHA-256; no runtime auto-download.
- [ ] **Step 4: Generate release manifest** git commit, container digests, lockfile hashes, model hashes, dataset bundle hash, schema/migration head.
- [ ] **Step 5: Commit** `chore: pin offline release dependencies`.

---

### Task 8: Create explicit offline Compose/release profile and prove no network dependency

**Files:**
- Create `docker-compose.offline.yml`.
- Create `scripts/offline_smoke.sh`.

**Interfaces:**
- Offline stack: web, api, postgres, redis, worker, neo4j, graph projector, evidence store volume; optional local model only if packaged.

- [ ] **Step 1: Ensure no service except optional collector has required egress**. Analysis services must run on internal networks; runtime does not pull packages/models.
- [ ] **Step 2: Prebuild images while network available** then execute offline smoke with Docker network configured internal/no egress as practical.
- [ ] **Step 3: Load demo replay bundle and run golden workflow** under offline mode.
- [ ] **Step 4: Open dashboard/report through localhost only.
- [ ] **Step 5: Kill Neo4j and prove core case/evidence APIs remain available; restart/rebuild graph.
- [ ] **Step 6: Kill optional model and prove deterministic extraction/report path remains usable.
- [ ] **Step 7: Commit** `test: prove DARKNETRA offline demo operation`.

---

### Task 9: Implement backup/restore and disaster-recovery verification

**Files:**
- Create `scripts/backup.sh`, `scripts/restore.sh`, `docs/operations/backup-restore.md`, tests/smoke.

**Interfaces:**
- Backup covers PostgreSQL dump, evidence store, release/config manifest. Redis excluded as transient; Neo4j may be excluded because rebuildable, with explicit rebuild step.

- [ ] **Step 1: Backup script creates timestamped archive/manifests and SHA-256**; no plaintext secret export unless explicitly required/encrypted outside repository scope.
- [ ] **Step 2: Restore into empty disposable stack**; apply migrations compatible with backup version.
- [ ] **Step 3: Verify evidence hashes after restore** and compare authoritative counts/selected IDs.
- [ ] **Step 4: Rebuild Neo4j from restored Postgres and compare graph parity.
- [ ] **Step 5: Commit** `ops: add verified backup and restore workflow`.

---

### Task 10: Create finale demo mode and presenter-safe UI state

**Files:**
- Create demo config/feature flag and `docs/demo/finale-runbook.md`.
- Modify UI only for safe demo badge/case shortcut; no fake backend result injection.

**Interfaces:**
- Demo case `SYN-DEMO-001`, source class visibly `SYNTHETIC`.

- [ ] **Step 1: Add persistent `SYNTHETIC DEMO` banner** when demo-case source class/config indicates replay mode; it must not appear for normal authorized cases.
- [ ] **Step 2: Add presenter shortcut only to open known synthetic case**, not bypass authentication/authorization.
- [ ] **Step 3: Seed deterministic analyst/reviewer accounts through demo provisioning script; credentials supplied at runtime and changed/removed after demo.
- [ ] **Step 4: Ensure restricted media stays blurred and no dangerous external links are clickable.
- [ ] **Step 5: Runbook exact sequence** login -> case -> evidence integrity -> entities -> activity -> link reasons -> accept synthetic link -> graph -> trend alert -> report.
- [ ] **Step 6: Commit** `feat: add clearly labelled synthetic finale demo mode`.

---

### Task 11: Record a failure-recovery rehearsal

**Files:**
- Create `docs/demo/failure-recovery.md`.

- [ ] **Step 1: Rehearse live network absent**; demo unaffected.
- [ ] **Step 2: Rehearse Neo4j unavailable**; show typed graph unavailable state, restart and rebuild.
- [ ] **Step 3: Rehearse Redis/worker restart**; preserved evidence/job state remains authoritative and retries recover.
- [ ] **Step 4: Rehearse local model unavailable**; deterministic validators/report still work and UI states model unavailable explicitly.
- [ ] **Step 5: Rehearse evidence tamper test in disposable clone**; integrity mismatch visible and expected digest unchanged.
- [ ] **Step 6: Record recovery commands and measured recovery outcomes, not hypothetical claims.
- [ ] **Step 7: Commit** `docs: rehearse finale failure recovery`.

---

### Task 12: Final release verification and evidence package

**Files:**
- Create `docs/verification/plan-07-evaluation-offline-demo.md`.
- Create release artifact directory through CI, not committed large binaries.

- [ ] **Step 1: Run entire repository quality/security suite** fresh.
- [ ] **Step 2: Run unified evaluation** and retain measured JSON/Markdown artifact.
- [ ] **Step 3: Run offline smoke + golden replay + E2E.
- [ ] **Step 4: Run backup/restore + Neo4j rebuild parity.
- [ ] **Step 5: Generate SBOM/security scans/release manifest.
- [ ] **Step 6: Record exact commit SHA, migration head, model hashes, image digests, dataset seed/hash, metrics and limitations.
- [ ] **Step 7: Commit verification document** `docs: verify offline finale release`.

---

## Plan 07 Definition of Done

- Synthetic dataset is deterministic, labelled, safe, and includes hard negatives/migrations/trends.
- Production algorithms cannot read hidden ground truth.
- Unified evaluation reports actual per-slice extraction, image, link and trend metrics plus ablations.
- Security/static/container/SBOM gates run and findings are documented.
- Dependencies, images and model assets are locked for release.
- Complete demo works offline from prebuilt assets without Tor/cloud LLM/GPU requirement.
- Evidence integrity, Redis/worker recovery, Neo4j loss/rebuild and model-unavailable scenarios are rehearsed.
- Backup/restore preserves hashes and authoritative state.
- Finale UI visibly labels synthetic demo data and does not bypass auth.
- Release verification records measured evidence, not predicted claims.

## Optional Plan 08 handoff

The product is competition-ready without Plan 08. Only if core Plans 01-07 are stable and written legal/competition approval exists should the team add the constrained public-source/Tor collector. The final demo must continue to work when that collector is disabled.