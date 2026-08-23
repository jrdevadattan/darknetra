# DARKNETRA Multilingual Extraction and Deterministic Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert safe evidence derivatives into evidence-linked, multilingual structured entities while using deterministic protocol validation for formal indicators and bounded local NLP for semantic entities.

**Architecture:** Extraction is layered and provenance-preserving: original derivative text -> normalization/script/language metadata -> deterministic candidate extractors -> protocol validators -> semantic/domain NER -> canonicalization -> immutable extraction observations in PostgreSQL. No model is allowed to invent an entity without a source span; raw strings are retained separately from normalized/canonical values.

**Tech Stack:** Python 3.12, FastAPI/SQLAlchemy, Celery, RapidFuzz, regex, Unicode tooling, Indic NLP/IndicXlit-compatible offline model/rules, GLiNER-compatible local model, phonenumbers, GnuPG restricted subprocess, bip-utils, eth-utils, Monero address parser, pytest/Hypothesis, React/TanStack Query.

## Global Constraints

- Begin only after Evidence Vault Plan 03 verification passes.
- Extract only from approved safe derivatives; never mutate source evidence.
- Every extracted entity MUST contain evidence/derivative ID, exact raw span offsets when text-based, extractor name/version, confidence/validation status, and canonical value when available.
- Deterministic protocol validation outranks model inference for PGP/wallet/contact/price/quantity syntax.
- Preserve exact source text. Unicode/transliteration/canonicalization is always a derived representation.
- Supported language focus: English, Hindi, Punjabi, Hinglish, Romanized Hindi, Romanized Punjabi. Unknown/other scripts remain preserved and tagged `und` rather than forced into a supported language.
- Drug/substance word alone does not establish a sale; Plan 05 handles transactional activity scoring.
- LLM output cannot create authoritative entities in this plan.
- Never execute PGP content, shell fragments, URLs, QR payloads, or imported instructions.
- Public/private crypto-address presence is an indicator only and does not identify a natural person.
- Never store private cryptographic keys in fixtures or source control.

---

## Canonical entity types

```text
SUBSTANCE
VENDOR_ALIAS
MARKETPLACE
LOCATION
SHIPPING_TERM
PACKAGING_TERM
PRICE
QUANTITY
CURRENCY
CONTACT_HANDLE
EMAIL
PHONE
PGP_KEY
PGP_FINGERPRINT
BTC_ADDRESS
ETH_ADDRESS
XMR_ADDRESS
URL
ONION_LOCATOR
IMAGE_REFERENCE
SLANG_CANDIDATE
```

---

### Task 1: Add extraction observation/taxonomy schema

**Files:**
- Create: `apps/api/darknetra_api/models/entity.py`
- Create: `apps/api/darknetra_api/models/taxonomy.py`
- Create: `apps/api/darknetra_api/schemas/entities.py`
- Create Alembic migration/tests.

**Interfaces:**
- Tables: `entity_observations`, `canonical_entities`, `taxonomy_terms`, `entity_entity_links` only for deterministic canonical equivalence, not operator identity.

- [ ] **Step 1: Write failing schema tests** for span bounds, immutable source evidence reference, entity type enum, extractor/version, confidence range `[0,1]`, validation status, raw/normalized/canonical separation.
- [ ] **Step 2: Implement models** with `start_offset/end_offset` nullable only for non-text artifacts; text observations require valid offsets enforced by service tests.
- [ ] **Step 3: Create taxonomy term fields** `canonical_name`, `term`, `language`, `script`, `term_type`, `active`, `source_note`, version timestamps. No real seller/contact lists belong in taxonomy fixtures.
- [ ] **Step 4: Generate/apply migration** and run schema tests.
- [ ] **Step 5: Commit** `feat: define evidence linked entity schema`.

---

### Task 2: Implement lossless Unicode/script/language preprocessing

**Files:**
- Create: `apps/api/darknetra_api/nlp/normalization.py`
- Create: `apps/api/darknetra_api/nlp/script.py`
- Create: `apps/api/tests/unit/nlp/test_normalization.py`

**Interfaces:**
- `NormalizedText(raw: str, normalized: str, char_map: tuple[int,...], script_tags: tuple[SpanTag,...])`.
- Char map enables normalized match to resolve back to original source offsets.

- [ ] **Step 1: Write tests** for Devanagari, Gurmukhi, Latin, mixed script, zero-width chars, homoglyph-like characters, combining marks, emoji, punctuation, multiple spaces, CRLF, invalid replacement chars.
- [ ] **Step 2: Implement conservative normalization**: canonical Unicode normalization for analysis, whitespace canonicalization, safe zero-width handling with warnings. Never overwrite `raw`.
- [ ] **Step 3: Build normalized-to-raw offset mapping** and property-test that every normalized extracted span resolves to a bounded raw span.
- [ ] **Step 4: Implement script tags** `Latn`, `Deva`, `Guru`, `Common`, `Unknown` per codepoint/span; do not infer nationality/identity.
- [ ] **Step 5: Commit** `feat: add lossless multilingual normalization`.

---

### Task 3: Implement Romanized Hindi/Punjabi normalization boundary

**Files:**
- Create: `apps/api/darknetra_api/nlp/transliteration.py`
- Create tests/manifest under `models/manifests/indic-transliteration.json`.

**Interfaces:**
- `generate_transliteration_candidates(text, target_script) -> list[Candidate]` with score/version; never replaces original text.

- [ ] **Step 1: Write tests** using harmless code-mixed phrases covering Hindi-English and Punjabi-English spelling variants; include ambiguous Roman words that must return multiple/low-confidence candidates rather than forced mapping.
- [ ] **Step 2: Implement offline model/rule adapter** behind interface; model path and SHA-256 come from manifest, not downloaded at request time.
- [ ] **Step 3: Add explicit confidence threshold** below which canonical match stays unlinked and is shown for analyst review.
- [ ] **Step 4: Ensure transliteration result stores model/version and source span provenance**.
- [ ] **Step 5: Commit** `feat: add Indic transliteration candidates`.

---

### Task 4: Implement deterministic quantity, price, contact, URL, and locator candidates

**Files:**
- Create: `apps/api/darknetra_api/extractors/patterns.py`
- Create: `apps/api/darknetra_api/extractors/commercial.py`
- Create tests.

**Interfaces:**
- Extractors return `EntityCandidate(type, raw_value, normalized_value, start, end, confidence, metadata)`; candidates are not persisted until validator/canonicalizer service accepts them.

- [ ] **Step 1: Write tests** for decimal separators, INR/USD/crypto-like price notation, mass/count units, ranges, minimum-order-like phrases, phone/email/handle formats, normal web URL and `.onion` locator string detection.
- [ ] **Step 2: Add negative tests** for dates mistaken as prices, article citations, version numbers, hashes, IPv6 fragments, ordinary `@` prose, scientific units unrelated to transaction context.
- [ ] **Step 3: Implement bounded regexes** with compiled patterns and maximum input chunk sizes to avoid regex DoS.
- [ ] **Step 4: Normalize units/currencies only when unambiguous**; preserve unresolved raw value otherwise.
- [ ] **Step 5: Validate phone candidates with `phonenumbers` only when region/context allows; do not invent country from unsupported text.
- [ ] **Step 6: Commit** `feat: extract deterministic commercial indicators`.

---

### Task 5: Implement OpenPGP public-key/fingerprint validation in isolated temporary home

**Files:**
- Create: `apps/api/darknetra_api/validators/pgp.py`
- Create tests with generated TEST-ONLY public keys under test runtime, not committed secret keys.

**Interfaces:**
- `inspect_public_key(armored: str) -> PgpInspection` returns version, computed fingerprint(s), public-key metadata safe for storage; rejects secret-key material.

- [ ] **Step 1: Write tests** generating ephemeral test public key in a temporary GNUPGHOME, exported public armor, malformed armor, fake textual fingerprint, and secret-key block rejection.
- [ ] **Step 2: Implement subprocess using argument list, never shell=True**. Use isolated `0700` temp GNUPGHOME and GnuPG machine-readable `--with-colons`/show-only behavior; enforce timeout and input-size limit.
- [ ] **Step 3: Compute/trust fingerprint from parser output**, never a fingerprint string merely written beside a key.
- [ ] **Step 4: Scrub temp home after inspection** and never import into developer/user keyring.
- [ ] **Step 5: Commit** `feat: validate OpenPGP indicators safely`.

---

### Task 6: Implement chain-specific cryptocurrency address validators

**Files:**
- Create: `apps/api/darknetra_api/validators/crypto.py`
- Create tests.

**Interfaces:**
- `validate_crypto_candidate(value: str) -> CryptoValidation | None`; supported `BITCOIN`, `ETHEREUM`, `MONERO`.

- [ ] **Step 1: Write positive/negative tests** from protocol-library/documentation test vectors, not real investigation wallets.
- [ ] **Step 2: Bitcoin** candidate regex only discovers; bip-utils/protocol parser validates Base58/Bech32/Bech32m checksum/network form. Store canonical string and detected network when determinable.
- [ ] **Step 3: Ethereum** validate 20-byte hex form; preserve checksum status (`valid_checksum`, `all_lower_no_checksum`, `invalid_checksum`). Do not silently checksum-correct a mixed-case invalid address.
- [ ] **Step 4: Monero** use maintained parser for allowed public address formats; never add private spend/view keys.
- [ ] **Step 5: Add context metadata** distinguishing address string observation from any later blockchain enrichment. Presence is not proof of control.
- [ ] **Step 6: Commit** `feat: validate cryptocurrency indicators`.

---

### Task 7: Implement domain taxonomy and semantic NER adapter

**Files:**
- Create: `apps/api/darknetra_api/nlp/domain_ner.py`
- Create: `apps/api/darknetra_api/nlp/taxonomy_matcher.py`
- Create local model manifest.
- Create tests with synthetic/harmless controlled terms and selected publicly documented drug names as classification labels, never procurement instructions.

**Interfaces:**
- Domain labels: `SUBSTANCE`, `VENDOR_ALIAS`, `LOCATION`, `SHIPPING_TERM`, `PACKAGING_TERM`, `MARKETPLACE`.
- `extract_semantic_entities(text, labels) -> list[ModelEntity]` local-only by default.

- [ ] **Step 1: Write matcher tests** for exact case-insensitive, Unicode-normalized, transliteration candidate, fuzzy typo threshold, and dangerous over-fuzzy short-token negatives.
- [ ] **Step 2: Implement taxonomy matcher** with type-specific RapidFuzz thresholds; terms <=4 chars require exact/explicit aliases to prevent false matches.
- [ ] **Step 3: Implement GLiNER-compatible adapter** loading model once per worker, offline from pinned manifest. If model unavailable, job records deterministic extractor results and explicit model-unavailable warning rather than failing entire evidence pipeline.
- [ ] **Step 4: Require source spans** from model output; discard malformed/out-of-range spans and audit model version in extraction run.
- [ ] **Step 5: Deduplicate overlapping taxonomy/model results** using deterministic precedence: protocol validators > exact taxonomy > high-confidence model > fuzzy/transliteration candidate.
- [ ] **Step 6: Commit** `feat: add local domain entity extraction`.

---

### Task 8: Implement canonicalization and entity persistence pipeline

**Files:**
- Create: `apps/api/darknetra_api/services/extraction.py`
- Create: `apps/api/darknetra_api/jobs/tasks/extraction.py`
- Create integration tests.

**Interfaces:**
- `extract_derivative(derivative_id, extractor_bundle_version)` idempotent.

- [ ] **Step 1: Write idempotency tests**: repeated task same bundle does not duplicate observations; new extractor version creates versioned run/observations without deleting old results.
- [ ] **Step 2: Implement pipeline ordering** normalization -> deterministic candidates/validation -> taxonomy/NER -> canonicalization -> persistence.
- [ ] **Step 3: Persist raw exact span and derived normalized/canonical values**; verify offsets against derivative text before insert.
- [ ] **Step 4: Build canonical entity merge rules** limited to exact validated identifiers and taxonomy equivalence. Do not merge vendor aliases based on stylometry/images here.
- [ ] **Step 5: Queue extraction automatically for eligible READY/PARTIAL text derivatives**.
- [ ] **Step 6: Commit** `feat: persist versioned evidence linked extraction`.

---

### Task 9: Implement slang/code-term candidate discovery without automatic narcotics labeling

**Files:**
- Create: `apps/api/darknetra_api/nlp/novel_terms.py`
- Create tests.

**Interfaces:**
- `NovelTermCandidate(term, normalized, frequency, source_diversity, known_taxonomy_match, score)`.

- [ ] **Step 1: Write tests** for unknown token repeated across sources, typo of known term, stopword/noise, random UUID/hash/base64, single-source spam.
- [ ] **Step 2: Filter structured noise** (wallets/hashes/URLs/IDs already extracted), stopwords, tiny tokens, high-entropy strings.
- [ ] **Step 3: Candidate score must include source/alias diversity**, not raw repeated count only.
- [ ] **Step 4: Persist only as `SLANG_CANDIDATE` / analyst-review observation**, never canonical substance until taxonomy analyst decision is added in later admin workflow.
- [ ] **Step 5: Commit** `feat: surface emerging terminology candidates`.

---

### Task 10: Build Entities API and exact-span retrieval

**Files:**
- Create/extend entity repositories/services/routes.
- Create tests.

**Interfaces:**
- `GET /api/v1/cases/{case_id}/entities`
- `GET /api/v1/cases/{case_id}/entities/{observation_id}`
- Filters: type, extractor, validation status, language/script, evidence ID, canonical entity.

- [ ] **Step 1: Write authorization/pagination/filter tests** and cross-case 404 tests.
- [ ] **Step 2: Response exposes redacted value according to type/role** plus `evidence_id`, `derivative_id`, raw span offsets, context excerpt generated server-side with bounded characters.
- [ ] **Step 3: Context endpoint sanitizes text and never interprets imported markup**.
- [ ] **Step 4: Add merge/split endpoint only for canonical taxonomy/entity management with mandatory rationale/audit; vendor identity merge remains Plan 05 analyst-link flow.
- [ ] **Step 5: Commit** `feat: expose case entity observations`.

---

### Task 11: Replace Entities UI shell with evidence-linked investigator table

**Files:**
- Create `apps/web/src/features/entities/**`.
- Replace case entities route.
- Create tests/E2E.

**Interfaces:**
- Entity row fields: type, redacted display value, canonical value when present, confidence/validation, source count, extractor, language/script.

- [ ] **Step 1: Write tests** proving clicking entity opens exact evidence context, deterministic validated indicators visibly differ from model confidence, and sensitive full-value reveal is not automatic.
- [ ] **Step 2: Implement filters/search/pagination** with URL query state.
- [ ] **Step 3: Implement evidence-context drawer** showing original string, normalized/canonical mapping, extractor/version, evidence ID, span and warnings.
- [ ] **Step 4: For PGP/wallet entities show protocol validation wording**, not identity/guilt wording.
- [ ] **Step 5: E2E from case -> Entities -> filtered wallet/PGP -> evidence context.
- [ ] **Step 6: Commit** `feat: add evidence linked entity review UI`.

---

### Task 12: Add extraction evaluation harness and multilingual slice metrics

**Files:**
- Create: `evaluation/extraction/score.py`
- Create: `evaluation/extraction/schema.json`
- Create synthetic labelled samples under `datasets/synthetic/extraction/` with fictional aliases and no operational source locators.
- Create tests.

**Interfaces:**
- Input labels include evidence text, entity type, exact offsets, canonical optional, language slice.
- Output JSON + Markdown metrics per entity type and language slice.

- [ ] **Step 1: Create held-out synthetic labels** for English, Hindi, Punjabi, Hinglish/Romanized Hindi, Romanized Punjabi with positive and negative contexts.
- [ ] **Step 2: Implement exact-span entity precision/recall/F1** plus protocol-validator precision; partial-overlap may be secondary diagnostic but not substitute main metric.
- [ ] **Step 3: Produce per-type/per-language table** so overall F1 cannot hide weak wallet/substance/location performance.
- [ ] **Step 4: Add command** `uv run python evaluation/extraction/score.py --dataset ... --output ...` and test deterministic output.
- [ ] **Step 5: Do not copy paper benchmark scores as project results**; report only observed run values.
- [ ] **Step 6: Commit** `test: add multilingual extraction evaluation`.

---

### Task 13: Final Plan 04 verification/documentation

**Files:**
- Create `docs/architecture/extraction.md`.
- Create `docs/verification/plan-04-extraction-indicators.md`.

- [ ] **Step 1: Document layered pipeline**, provenance, language handling, formal validators, model fallback, canonicalization and limitations.
- [ ] **Step 2: Run fresh full suite** plus extraction scorer.
- [ ] **Step 3: Record actual metrics by entity/language, model manifest hashes, extractor bundle version and commit SHA.
- [ ] **Step 4: Commit** `docs: verify extraction milestone`.

---

## Plan 04 Definition of Done

- Text normalization is lossless with raw/derived separation and reversible span mapping.
- Hindi/Punjabi/Hinglish/Romanized handling is explicit and model/rule versions are recorded.
- Prices/quantities/contacts/URLs and formal indicators use deterministic candidates/validation where appropriate.
- OpenPGP fingerprint is computed from parsed public key, not trusted from adjacent text.
- BTC/ETH/XMR address strings are chain-validated using test vectors; presence is not identity proof.
- Semantic NER runs locally/offline and cannot create spanless entities.
- Novel/slang terms are review candidates, not automatically labelled narcotics.
- Every observation links to evidence/derivative exact context.
- Entities UI communicates validation vs model confidence accurately.
- Evaluation reports real project metrics per entity type/language.

## Plan 05 handoff contract

Plan 05 may consume canonical entities/observations, validated PGP/crypto/contact indicators, normalized text, safe image derivatives and evidence timestamps. It must treat stylometry/image/operational similarity as analytic signals, not deterministic identity proof.