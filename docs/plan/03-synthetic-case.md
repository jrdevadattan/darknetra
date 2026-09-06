# Plan 03 — Synthetic case SYN-CHD-001: generator, ground truth, seed, eval questions

Milestone M1 · Owner E · Depends on 02 (upload API) · Used by every later plan's tests and by the demo.

**Goal.** A deterministic, clearly synthetic case that exercises every lane: multilingual chat exports, marketplace listings, PGP keys, wallets with an Elliptic-format ledger, images with a near-duplicate, a negative-context document, chat screenshots, a planted alias link, a decoy false link, and a planted trend. Ground truth stays outside the application and drives the tests and the eval set.

**Architecture.** `data/synthetic/generator.py --seed 20260906 --out data/synthetic/out/SYN-CHD-001` writes a bundle and a manifest; `backend/scripts/seed_synthetic_case.py` pushes it through the public API exactly like an investigator would, then records the filename → evidence-code map for tests. Nothing is inserted directly into the database.

---

## Files

```
data/synthetic/
├── generator.py              entry point; pure functions per artefact; seeded random
├── personas.py               operators, aliases, handles, keys, wallets, images
├── text_templates.py         Hinglish / Punjabi / English message and listing templates with slots
├── lexicon_seed.yaml         classification terms used by the generator and by plan 04's lexicon seed
├── README.md                 what is in the bundle, what is planted, how to regenerate
└── out/SYN-CHD-001/          generated (gitignored except manifest.json and ground_truth.json)
    ├── bundle.zip            everything below except ground_truth.json
    ├── telegram_export/result.json (+ photos/)      Telegram Desktop export
    ├── whatsapp/WhatsApp Chat with KMK.txt           WhatsApp export
    ├── listings/kali_maal_kk.html, kmk_profile.html, whiteline_pb.html, northstar_meds.html
    ├── keys/kali_maal_kk.asc, whiteline_pb.asc       test-only public keys
    ├── ledger/nodes.csv, edges.csv, address_map.csv   Elliptic-format subgraph (102 features)
    ├── images/product_a.jpg, product_a_copy.jpg, unrelated.jpg, chat_screenshot_1.png, chat_screenshot_2.png
    ├── docs/seizure_memo.pdf                          negative-context document
    ├── manifest.json                                  files, sha256, intended source_class, notes
    └── ground_truth.json                              NOT in bundle; read only by tests and evals
backend/scripts/seed_synthetic_case.py
backend/evals/questions.yaml
tests/scenarios/test_synthetic_bundle.py
```

---

## Personas and planted structure

| Persona | Surface | Signals | Purpose |
|---|---|---|---|
| Operator 1 | listing vendor `kali_maal_kk`; chat handle `KMK.Zirakpur` | same PGP key K1 (listing block and pasted in chat on day 3); product photo A in listing, re-compressed crop in chat; Wickr id `kmk_drop` in both; wallet W1 (bech32) in chat | the STRONG link (≥ 2 families) |
| Operator 2 (decoy) | listing vendor `whiteline_pb` | pays into escrow wallet W_escrow that also appears on Operator 1's listing as the market escrow; PGP key K2; different photo | the false link that must stay WEAK |
| Operator 3 | listing vendor `northstar_meds` | unrelated everything; English only | noise |
| Buyers | chat participants `rahul_zk`, `bunty_m`, `preet.k` | Hinglish and Punjabi, quantities in g and tola, prices in ₹ | multilingual extraction |
| News | `seizure_memo.pdf` | substances named, "seized", "police", no offer or price | negative context |

Planted trend: the phrase `safed line` is absent on days 1–4 and appears on days 5–10 from three different senders and in an edited listing description (source diversity ≥ 3). Control term `purani cheez` appears on every day from one sender only (must not alert).

Wallets: W1 → maps to an Elliptic node labelled illicit (class 1) inside timestep ≤ 34; W2 (buyer) → licit node; W_escrow → tagged `shared_service` in `address_map.csv`; one Tron address `T…` (valid base58check) in the WhatsApp chat; one ETH address with valid EIP-55; one Monero-shaped string.

Images: `product_a.jpg` (PIL: packet shape, label text, noise), `product_a_copy.jpg` (crop 5%, JPEG quality 40, brightness +8%), `unrelated.jpg` (gradient with shapes). Expected pHash distance ≤ 6 for the pair, ≥ 20 for unrelated. `chat_screenshot_1.png`/`_2.png` render six chat bubbles with Hinglish text and timestamps for the vision-transcription tool.

PGP: two RSA-2048 keys generated at build with `pgpy`; only public armour written; fingerprints in ground truth. Never write private keys to disk.

---

## Ledger (Elliptic-format subgraph)

Two paths, chosen at generation time:

1. **Dataset present** (`data/elliptic/elliptic_txs_features.csv`, `elliptic_txs_classes.csv`, `elliptic_txs_edgelist.csv`, and `models/gnn/temporal_X_scaled.npy` + `temporal_scaler.pkl`): pick two illicit and two licit nodes at timestep ≤ 34; take their 2-hop neighbourhoods (cap 300 nodes); recover raw 102-dim features with `scaler.inverse_transform(temporal_X_scaled[idx])` (the predictor re-applies the scaler); write `nodes.csv` (node_index, txid, timestep, label, f_0…f_101), `edges.csv` (src, dst by node_index), `address_map.csv` (synthetic address → node_index, tag). Record dataset provenance in `manifest.json`.
2. **Dataset absent**: generate features by sampling per-column means and standard deviations from `temporal_scaler.pkl` (`scaler.mean_`, `scaler.scale_`), and a random graph; label two nodes illicit. The GNN then runs but its output is not meaningful; `manifest.json` says so and the UI caveat covers it.

`address_map.csv` columns: `address, chain, node_index, tag` where tag ∈ `{vendor_controlled, buyer, shared_service, unknown}`.

---

## Text generation

Templates with slots, e.g. `"{qty} {unit} {substance_slang} chahiye, {price} mein hoga? {route}"` with slot pools: quantities (`2`, `5`, `10`, `ek`, `do`), units (`gm`, `gram`, `tola`, `pieces`), slang from `lexicon_seed.yaml` (classification terms only, e.g. `maal`, `chitta`, `safed`, `kaala`, `line`, `pudiya`), prices (`1500`, `₹2,500`, `Rs 3k`), routes (`Zirakpur se`, `Mohali wale route`, `courier bhej dunga`), times. Punjabi lines in Gurmukhi and in Roman Punjabi. 300 Telegram messages over 10 days with realistic hours; 50 WhatsApp messages. Every message that carries a planted signal is listed in ground truth with its message index.

Do not generate procurement instructions, real vendor names, real contact details or real onion addresses. Onion locators in listings use the reserved test form `<56 chars from the seed>.onion` marked `SYNTHETIC` in the page footer.

---

## ground_truth.json

```json
{
  "case_code_hint": "SYN-CHD-001",
  "source_class": "SYNTHETIC",
  "files": {"telegram_export": "telegram_export.zip", "...": "..."},
  "aliases": {
    "same_operator": [["kali_maal_kk", "KMK.Zirakpur"]],
    "decoy_pairs": [["kali_maal_kk", "whiteline_pb"]],
    "signals": {"kali_maal_kk|KMK.Zirakpur": ["pgp_fingerprint", "image", "contact"]}
  },
  "pgp": {"K1": {"fingerprint": "…", "seen_in": ["listings/kali_maal_kk.html", "telegram:msg:143"]}, "K2": {...}},
  "wallets": {"W1": {"address": "bc1q…", "expected_gnn_class": 1, "tag": "vendor_controlled"}, "W_escrow": {"address": "bc1q…", "tag": "shared_service"}},
  "planted_messages": {"pgp_paste": 143, "wallet": 88, "wickr": 120, "trend_first": 201},
  "trend": {"term": "safed line", "first_day": 5, "senders": 3, "control_term": "purani cheez"},
  "negative_context": ["docs/seizure_memo.pdf"],
  "images": {"near_duplicate": ["images/product_a.jpg", "images/product_a_copy.jpg"], "unrelated": "images/unrelated.jpg"},
  "expected_observation_min": {"BTC_ADDRESS": 3, "PGP_FINGERPRINT": 2, "PRICE": 20, "QUANTITY": 20, "SUBSTANCE": 30, "CONTACT_HANDLE": 3, "TRON_ADDRESS": 1, "ETH_ADDRESS": 1}
}
```

---

## Seed script

`backend/scripts/seed_synthetic_case.py [--if-missing | --reset] [--bundle PATH] [--api http://127.0.0.1:8000]`

1. Ensure users: `administrator` (bootstrap via CLI if absent) and `analyst.demo` (INVESTIGATOR). Passwords from env; never printed.
2. Login as `analyst.demo`; create case `{title: "SYN-CHD-001 synthetic demo", demo: true, source_policy: {allowed_source_classes: [SYNTHETIC, UPLOAD, OSINT_SURFACE, CHAIN], person_lookup_enabled: true}}`.
3. Upload `bundle.zip` with `source_class=SYNTHETIC`; then upload the standalone files listed in `manifest.json` that must be separate evidence rows (listings, keys, images, memo, screenshots, ledger CSVs).
4. Poll `GET /evidence` until no `PROCESSING`; assert no `FAILED` except the ones the manifest marks as expected.
5. Write `data/synthetic/out/seed_result.json`: `{case_id, case_code, files: {filename: evidence_code}}`.
6. `--reset`: archive the previous demo case, create a new one (evidence is never deleted).

---

## Eval questions (`backend/evals/questions.yaml`)

Ten questions with expected evidence codes resolved through `seed_result.json` at run time, e.g.:

1. "Which wallets appear in the Telegram chat?" → expects the message carrying W1.
2. "What PGP fingerprints are in the case and where?" → listing K1 and message 143.
3. "Which seller handles could be the same operator?" → STRONG pair, must mention PGP and image; must not assert identity.
4. "Is whiteline_pb linked to kali_maal_kk?" → must say weak, escrow reason.
5. "What quantities and prices are discussed on day 2?" → three messages.
6. "Is bc1q…(W1) linked to illicit activity?" → GNN above threshold with caveat.
7. "Any new slang this week?" → `safed line`, not `purani cheez`.
8. "What does the seizure memo say about a sale?" → no sale; negative context.
9. "Summarise message 88 in English." → wallet message translated, cited.
10. "Which images are near-duplicates?" → the pair.

Each entry: `question`, `expected_codes` (filenames), `must_include` phrases, `must_not_include` phrases (e.g. "is guilty", "confirmed identity"), `lane` (evidence|analytics|chain).

---

## Tasks

- [ ] **T1 personas + keys + wallets**: generation with `pgpy`, `bech32`, base58check; unit tests validate every generated identifier with plan 04's validators (import allowed in tests).
- [ ] **T2 text generation**: templates and slots; 300 + 50 messages; planted indices recorded.
- [ ] **T3 listings + images + PDF + screenshots**: Jinja templates, PIL renders, `fpdf2` memo.
- [ ] **T4 ledger**: both paths; tests assert 102 columns and address map integrity.
- [ ] **T5 bundle + manifest + ground truth**: deterministic bytes for a given seed (test: two runs produce identical hashes except PGP keys, which are re-generated only when `--regen-keys`).
- [ ] **T6 seed script**: through the API; idempotent with `--if-missing`; `seed_result.json`.
- [ ] **T7 eval questions** file + loader used by plans 05 and 06.

## Acceptance gate

`python data/synthetic/generator.py --seed 20260906` produces the bundle; `scripts/seed_synthetic_case.py` ingests it through the API in under 3 minutes on a laptop; `tests/scenarios/test_synthetic_bundle.py` asserts the planted structure exists in the store after plans 04 and 07 land (skips those checks before).
