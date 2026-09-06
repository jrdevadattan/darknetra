# Plan 04 — Extraction: normalisation, validators, lexicon, NER, canonicalisation, novel terms

Milestone M2 · Owner B · Depends on 02.

**Goal.** Turn text derivatives into evidence-linked observations with exact spans: deterministic protocol validators for wallets, keys, contacts and commerce; a multilingual lexicon matcher for substances, slang, places and shipping terms; a local NER pass as a lower-confidence second opinion; canonical entities for validated identifiers; and analyst-review candidates for unknown repeated terms. No model may invent an entity without a span.

**Architecture.** Layered and provenance-preserving: raw text → `NormalizedText` (with a char map back to raw) → candidates from validators and lexicon → NER → precedence and dedupe → canonicalisation → persistence in an `extraction_run`. Idempotent per `(evidence_id, bundle_version)`.

---

## Files

```
darknetra/extract/
├── models.py              ExtractionRun, Observation, CanonicalEntity, TaxonomyTerm
├── normalize.py           NormalizedText, normalize()
├── scripts_.py            script_spans(text) → [(start, end, "Latn"|"Deva"|"Guru"|"Common"|"Other")]
├── translit.py            candidates(text, target) → [Candidate(text, score)]
├── validators/
│   ├── base.py            Candidate(type, raw, normalized, start, end, validator, valid, confidence, meta)
│   ├── crypto.py          find_crypto(text) → BTC/ETH/TRON/XMR candidates
│   ├── pgp.py             find_pgp(text) → key blocks (computed fingerprints) + textual fingerprints
│   ├── contacts.py        emails, phones, handles, urls, onion locators
│   └── commerce.py        prices, quantities, currencies
├── lexicon.py             Lexicon.load(session), match(normalized) → candidates (SUBSTANCE, SLANG, LOCATION, SHIPPING_TERM, PACKAGING_TERM, MARKETPLACE, VENDOR_ALIAS hints)
├── ner.py                 GLiNER adapter behind a manifest; graceful absence
├── precedence.py          resolve(candidates) → deduped, ordered
├── canonical.py           canonicalise(session, case_id, observations)
├── novel_terms.py         discover(session, case_id) → SLANG_CANDIDATE observations
├── pipeline.py            run_evidence(evidence_id, bundle_version), run_case(case_id)
├── versions.py            BUNDLE_VERSION = hash(component versions + lexicon version)
darknetra/api/v1/routes/entities.py (replace stubs)  admin taxonomy routes
data/lexicon/terms.yaml    seed lexicon (classification terms only)
models/manifests/gliner.json  {name, repo, revision, sha256, labels}
alembic/versions/0004_extraction.py
tests/unit/extract/test_normalize.py test_scripts.py test_translit.py test_crypto.py test_pgp.py test_contacts.py test_commerce.py test_lexicon.py test_ner_adapter.py test_precedence.py test_novel_terms.py
tests/integration/test_extraction_pipeline.py test_entities_api.py
```

---

## Interfaces

### Normalisation

```python
@dataclass(frozen=True)
class NormalizedText:
    raw: str
    normalized: str
    to_raw: tuple[int, ...]         # to_raw[i] = raw offset of normalized[i]; len == len(normalized)+1 (end sentinel)
    scripts: tuple[ScriptSpan, ...]
    warnings: tuple[str, ...]       # e.g. "zero_width_removed:3"
def normalize(raw: str) -> NormalizedText
def raw_span(nt: NormalizedText, start: int, end: int) -> tuple[int, int]
```

Rules: NFC; CRLF → LF; runs of spaces/tabs → one space; zero-width (U+200B–U+200D, U+FEFF, U+200E/F) removed with a warning; combining marks preserved; no case folding here (matchers casefold locally). Property test: for random raw strings, every normalized index maps to a raw index such that `raw[to_raw[i]]` equals `normalized[i]` or the removed/collapsed character class.

### Scripts

Unicode ranges: Devanagari U+0900–U+097F, Gurmukhi U+0A00–U+0A7F, Latin basic/extended, Common (digits, punctuation, emoji), Other. `script_spans` merges adjacent codepoints of the same script.

### Transliteration

`indic_transliteration.sanscript` for Devanagari ↔ ITRANS/HK/IAST and Gurmukhi ↔ ITRANS; Roman-to-Indic candidates use the lexicon's known variants first, then sanscript with ITRANS as the best-effort scheme; each candidate carries a score (`1.0` lexicon variant, `0.6` scheme output). Used for lexicon matching and for index-time expansion (plan 05). Never replaces raw spans.

### Validators (each returns candidates with raw-offset spans)

- **crypto.py**
  - Bitcoin: regex candidates `\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b` (base58check: version 0x00/0x05, double-SHA256 checksum), `\b(bc1|tb1)[a-z0-9]{25,90}\b` (bech32 for witness v0, bech32m for v1+; HRP `bc`/`tb`; `meta.network`, `meta.type ∈ {p2pkh,p2sh,p2wpkh,p2wsh,p2tr}`). Invalid checksum → `valid=false, confidence=0.3`.
  - Ethereum: `\b0x[0-9a-fA-F]{40}\b`; `meta.checksum ∈ {valid_checksum, all_lower, all_upper, invalid_checksum}` via `eth_utils.is_checksum_address`; invalid mixed-case → `valid=false`.
  - Tron: `\bT[1-9A-HJ-NP-Za-km-z]{33}\b`; base58 decode → 25 bytes, prefix 0x41, checksum first 4 bytes of sha256(sha256(payload)).
  - Monero: `\b[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b` → `validator="shape"`, `confidence=0.8`, `meta.traceable=false`.
  - Exclusions: hex strings that are SHA-256/MD5, tx ids (64 hex) → `TX_ID`? Not a type; skip. IPv6, UUIDs, base64 blobs → rejected by the checksum anyway.
- **pgp.py**
  - Armoured blocks `-----BEGIN PGP PUBLIC KEY BLOCK-----…END-----` → `pgpy.PGPKey.from_blob`; require `key.is_public`; secret blocks → candidate `PGP_KEY` with `valid=false`, `meta.secret=true`, and a warning observation (never stored beyond the span); fingerprint from `key.fingerprint` (uppercase, groups of 4) → `PGP_FINGERPRINT` with `validator="pgpy_computed"`, `confidence=1.0`; also `meta.userids` (emails in user IDs become EMAIL candidates with `meta.from_key=true`), `meta.created`, `meta.algo`.
  - Textual fingerprints: `\b(?:[0-9A-Fa-f]{4}[  ]?){10}\b` → `validator="regex"`, `confidence=0.6`; if a computed fingerprint exists in the same derivative and differs while the text claims it belongs to that key (within 300 chars), add `meta.mismatch=true`.
  - Signed messages `-----BEGIN PGP SIGNED MESSAGE-----`: record `PGP_SIGNED_TEXT` span in meta of a `PGP_KEY`? Keep simple: ignore, but log a warning.
- **contacts.py**
  - Email: RFC-ish regex, casefold, `validator="regex"`, `confidence=0.9`.
  - Phone: `phonenumbers.PhoneNumberMatcher(text, "IN", leniency=VALID)`; also raw 10-digit `[6-9]\d{9}` with separators; normalized E.164; `confidence=0.9` when parsed valid, `0.6` for bare 10-digit.
  - Handles: `(?<![\w@])@([A-Za-z0-9_.]{3,32})\b` (Telegram/Instagram-style), `t\.me/([A-Za-z0-9_]{5,32})`, `wickr[:\s-]+([A-Za-z0-9_.-]{3,32})`, `session\s*id[:\s]+(05[0-9a-f]{64})`, `signal[:\s]+(\+?\d{10,15})`; `meta.platform`.
  - URLs: `https?://[^\s<>"']+`; `.onion` v3: `\b[a-z2-7]{56}\.onion\b` → `ONION_LOCATOR` (`validator="v3_shape"`, `confidence=1.0`); v2 16-char onions flagged `deprecated`.
- **commerce.py**
  - PRICE: currency then amount or amount then currency: `(₹|Rs\.?|INR|USD|\$|€|BTC|USDT|TRX)\s?(\d[\d,]*(?:\.\d+)?)\s?(k|K|lakh|L)?` and `(\d[\d,]*(?:\.\d+)?)\s?(k|K|lakh)?\s?(rupay|rupaye|rupees|rs|inr|usd|dollars|btc|usdt)`; Indian grouping `1,50,000`; `k` → ×1000, `lakh` → ×100000; normalized `{"amount": 2500.0, "currency": "INR"}`; ranges `1500-2000` → two candidates with `meta.range=true`.
  - QUANTITY: `(\d+(?:\.\d+)?|ek|do|teen|char|paanch|adha|आधा|एक|दो|ਇੱਕ|ਦੋ)\s?(g|gm|gms|gram|grams|kg|kilo|tola|tole|pcs|pieces|piece|strip|strips|tab|tabs|tablet|ml|litre|liter|pudiya|puriya)\b`; word numbers mapped; units normalised: `tola = 11.6638 g`, `kg = 1000 g`, `adha = 0.5`; `normalized = {"value": 2, "unit": "tola", "grams": 23.33}` where convertible.
  - Negative tests: dates (`12/05/2026`), times (`10:30`), versions (`v2.1`), hashes, phone numbers, message ids, `5 min`, `2 km`.

### Lexicon

`data/lexicon/terms.yaml`:

```yaml
version: 1
terms:
  - canonical: heroin
    type: SUBSTANCE
    variants:
      - {term: chitta, language: pa, script: Latn}
      - {term: ਚਿੱਟਾ, language: pa, script: Guru}
      - {term: चिट्टा, language: hi, script: Deva}
      - {term: safed, language: hi, script: Latn, note: "white; ambiguous, needs context"}
  - canonical: generic_drug_term
    type: SLANG
    variants: [{term: maal, language: hi, script: Latn}, {term: माल, language: hi, script: Deva}]
  - canonical: Zirakpur
    type: LOCATION
    variants: [{term: zirakpur}, {term: ज़ीरकपुर}, {term: ਜ਼ੀਰਕਪੁਰ}]
  - canonical: courier_delivery
    type: SHIPPING_TERM
    variants: [{term: courier}, {term: bhej dunga}, {term: delivery}]
```

Loaded into `taxonomy_terms` by migration seed and editable via `/admin/taxonomy`. Matcher: casefolded NFC exact match on word boundaries for every variant and its transliteration candidates; RapidFuzz `partial_ratio` for terms ≥ 5 chars with thresholds 94 (5–7 chars) and 90 (≥ 8); terms ≤ 4 chars exact only. Ambiguous terms (note contains "ambiguous") get `confidence=0.5` unless another SUBSTANCE or QUANTITY candidate sits within 40 chars, then `0.75`. Every match records `term_id`, `language`, `script`, `validator="lexicon_exact|lexicon_fuzzy|lexicon_translit"`.

### NER

```python
class NerAdapter(Protocol):
    available: bool
    def extract(self, text: str, labels: Sequence[str]) -> list[NerSpan]   # NerSpan(label, start, end, score)
class GlinerAdapter(NerAdapter)  # loads once per process from models/manifests/gliner.json (repo + revision + sha256 verified), threshold 0.5, windows of 384 tokens with 64 overlap, spans mapped back
class NullAdapter(NerAdapter)    # available=False
```

Labels: `SUBSTANCE, VENDOR_ALIAS, LOCATION, SHIPPING_TERM, PACKAGING_TERM, MARKETPLACE`. Spans outside the text or overlapping a validator span are discarded. Model absence sets `extraction_runs.stats.ner="unavailable"`; the run still succeeds.

### Precedence and dedupe

Order: protocol validator (valid) > lexicon exact > lexicon translit > NER (score ≥ 0.7) > lexicon fuzzy > NER (< 0.7) > validator (invalid). Overlapping spans: keep the higher-precedence candidate; equal precedence → longer span; ties → earlier start. Same `(type, normalized, start, end)` → one observation.

### Canonicalisation

Only for validated identifiers and taxonomy equivalence: `BTC_ADDRESS`, `ETH_ADDRESS` (lowercased), `TRON_ADDRESS`, `PGP_FINGERPRINT` (computed only), `EMAIL`, `PHONE` (E.164), `CONTACT_HANDLE` (platform + casefold), `ONION_LOCATOR`, and lexicon terms → `canonical_entities(type, value)` upsert with `first_seen_at/last_seen_at` from evidence `captured_at`, `observation_count`. Vendor aliases are never merged here.

### Novel terms

Tokens in Latin/Devanagari/Gurmukhi words of 4–20 chars, not stopwords (English, Hindi, Punjabi lists), not lexicon variants, not inside any validator span, not high-entropy (Shannon entropy > 3.5 bits/char for Latin), frequency ≥ 3 across ≥ 2 evidence items or ≥ 2 senders → `SLANG_CANDIDATE` observation per first occurrence with `meta.frequency`, `meta.diversity`, `meta.score = ln(1+freq) * diversity`. Runs per case after extraction; never writes to the lexicon.

### Pipeline

```python
async def run_evidence(session, evidence_id, bundle_version=BUNDLE_VERSION) -> ExtractionRun
async def run_case(session, case_id) -> list[ExtractionRun]
```

Steps: load TEXT derivative (or MESSAGES flattened) → `normalize` → validators on `nt.normalized` (spans mapped to raw via `raw_span`) → lexicon → NER → precedence → verify every span against the derivative text (`text[start:end] == raw`) → persist observations under a new `extraction_run` (status RUNNING → DONE/FAILED, stats counts by type) → canonicalise → emit `store.changed(observation)` → schedule `novel_terms.discover(case_id)` debounced 30 s. Re-running with the same bundle version is a no-op (returns the existing run); a new bundle version creates a new run and new observations; old observations remain with their run id.

### Endpoints (replace stubs)

- `GET /cases/{id}/entities?type&validator&min_confidence&evidence_id&q&cursor&limit` → grouped by canonical entity `{entity, observation_count, first_seen, last_seen, sample_spans[3]}`; ungrouped types (PRICE, QUANTITY, SLANG_CANDIDATE) listed as observations.
- `GET /cases/{id}/entities/{entity_id}` → observations with spans and evidence codes, related edges (plan 07).
- `GET /cases/{id}/observations/{obs_id}` → observation + 200-char context.
- `POST /cases/{id}/extraction/run {evidence_id?}`; `GET /cases/{id}/extraction/runs`.
- `/admin/taxonomy` GET/POST/PATCH (ADMIN_TAXONOMY); PATCH bumps `lexicon_version` → new `BUNDLE_VERSION`.

---

## Tasks

- [ ] **T1 normalize + scripts + translit** with property tests (Hypothesis) and Devanagari/Gurmukhi fixtures.
- [ ] **T2 crypto validators** with BIP-173/350 vectors, EIP-55 vectors, Tron USDT contract address `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` (valid) and a mutated copy (invalid), Monero shape; negative vectors.
- [ ] **T3 pgp**: keys generated in-test with pgpy; secret-block rejection; textual fingerprint and mismatch.
- [ ] **T4 contacts + commerce** with positive and negative tables; Indian grouping; word numbers; tola conversion.
- [ ] **T5 lexicon** loader, matcher, thresholds, ambiguity rule; seed YAML.
- [ ] **T6 NER adapter** with manifest verification and NullAdapter path; test uses a stub model.
- [ ] **T7 precedence + canonical + novel terms**.
- [ ] **T8 pipeline + migration 0004 + endpoints**; idempotency and versioning tests; scenario 11, 12 tests.

## Acceptance gate

On SYN-CHD-001: observation counts meet `ground_truth.expected_observation_min`; planted fingerprint observed twice with `pgpy_computed`; W1 observed with `bech32_checksum valid`; every observation's `text[start:end] == raw` (integration assertion over all rows); scenarios 9–12 pass.

## Handoff

Plan 05 indexes chunks with lexicon variants; plan 07 consumes canonical entities and observations.
