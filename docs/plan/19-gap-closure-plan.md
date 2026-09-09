# Plan 19 — Gap closure: missing backend features found by the 8 September audit

Post-build · Owners A (harness, tools), B (extraction), C (analytics, monitoring) · Depends on plan 18 for the environment.

Priorities are ordered by what a judge will notice on 9 September. **P0** is demo-critical and each item is a few hours at most; **P1** is strong differentiation, one to two days each; **P2** is post-hackathon. Every item keeps the invariants in `AGENTS.md`: read-only sources, capture before reasoning, explicit unavailability, no fabricated results.

---

## P0 — demo-critical (today)

### P0-1 Live harness on stage
- What: configuration only (plan 18 §2). Add a smoke test `tests/integration/test_live_harness.py` marked `live` that posts one question to the seeded case and asserts `verification.ok` and `cost_usd > 0`.
- Acceptance: the six demo questions return cited answers with harness `CLAUDE` (or `OFFLINE`) and the replay cache is warm.

### P0-2 Working web search entry point
- Files: `tools/impl/research.py`, `tests/unit/test_research_parsers.py`, `.env.example`.
- Steps:
  1. Provision the public SearXNG endpoint (plan 18 §4) and set `DARKNETRA_SURFACE_SEARCH_SEARXNG_URL`.
  2. Detect the DuckDuckGo challenge explicitly: when the captured page has HTTP 202 or no `.result` and no `.no-results`, raise `ToolError("UNAVAILABLE", "DuckDuckGo served a bot challenge; configure SearXNG")` with `detail.http_status`, so the UI shows the reason instead of "no recognizable results".
  3. Make `web_search` (the raw DDG capture used by monitoring's `KEYWORD` default) route to SearXNG when configured, matching `surface_search`.
- Tests: fixture of the captured 202 page; SearXNG JSON fixture with `unresponsive_engines`.
- Acceptance: `reuse_smoke.py --search-provider searxng` returns ≥ 1 result; a monitoring `KEYWORD` item produces a hit through SearXNG.

### P0-3 Ahmia adapter follows the real search flow
- Files: `tools/impl/robin.py`, `tools/impl/surface.py`, `integrations/robin.py`, tests with a recorded fixture.
- Steps: record what Ahmia returns for a search from a browser (the site redirected `/search/?q=` to `/` for both the container and a desktop browser today); implement the working request shape (headers or path Ahmia expects), treat a redirect to `/` as `UNAVAILABLE: index returned its homepage` rather than parsing it; keep the Robin parser for the results page; add `robin_search` to the stale MCP test set (P0-6).
- Acceptance: `robin_search {"query":"Tor Project"}` returns index hits with `evidence_code`; otherwise an explicit unavailable reason. If Ahmia stays closed to automation, keep the pre-captured fixture and say so in the UI.

### P0-4 Demo data hygiene
- Archive the twelve `SYNTHETIC interface verification …` and `… diagnostics` cases (`POST /cases/{id}/close` then `/archive`) so the sidebar shows `CHD-2026-0002` first; add an archived filter default to the case list (plan 20).
- Seed a `WALLET` watchlist item for W1 and a `KEYWORD` item for the planted phrase so the alert fires in demo mode; escalate one alert into a finding before the pitch.
- Acceptance: the walkthrough passes against the cleaned database; the sidebar shows one demo case.

### P0-5 Trends and Wallets in the UI
- Backend is ready (`GET /trends`, `GET /wallets`, `POST /wallets/assess`); plan 20 items U1 and U2.

### P0-6 Stale MCP test
- File: `backend/tests/integration/test_stdio_mcp.py` line ~77: add `robin_search` to the expected set (or derive the expected set from the registry for the CASE_LEAD role). Acceptance: `manage.py test` fully green.

### P0-7 Retrieval eval path
- `backend/scripts/run_retrieval_eval.py`: default `--seed-result` should resolve relative to the repository root that ran the seed, or the seed should write `seed_result.json` into the worktree; document the flag. Acceptance: the command runs without arguments from either checkout.

---

## P1 — strong differentiation (one to two days each)

### P1-1 Vision transcription and OCR for chat screenshots
- Files: `tools/impl/evidence.py` (`transcribe_image`), `ingest/dispatch.py` (OCR derivative), `Dockerfile` (`tesseract-ocr tesseract-ocr-hin tesseract-ocr-pan`), `config.py` (`ocr_backend: none|tesseract|claude_vision`).
- Steps: when a Claude key exists, send the stored image to `claude-sonnet-5` with a fixed transcription prompt and store blocks with regions as an `OCR` derivative; otherwise Tesseract via `pytesseract` with `hin+pan+eng`; index the derivative; the tool returns blocks with evidence code and region.
- Tests: fixture screenshot from the synthetic generator; Tesseract path and stubbed vision path.
- Acceptance: `POST /tools/transcribe_image/health` → `ok`; "What does the chat screenshot say?" answers with `[E-0012 OCR block 3]` citations.

### P1-2 GNN wallet risk end to end
- Files: `models/gnn/` (copied artefacts + `predict.py`), `backend/pyproject.toml` extra `gnn` (`torch`, `torch-geometric`, CPU wheels), `backend/Dockerfile` build arg `DARKNETRA_GNN`, `analytics/gnn.py` (already imports `models/gnn/predict.py`).
- Steps: copy artefacts; build with the extra; import the synthetic ledger through `POST /cases/{id}/ledger/import`; make the seed script import it automatically when the CSVs exist.
- Acceptance: `assess_wallet` on W1 returns `illicit_probability` with `threshold 0.7167` and the F1 0.58 caveat; the report's wallet section shows it.

### P1-3 ETH and TRON chain adapters
- Files: `tools/impl/surface.py` (`chain_lookup`), `tools/adapters/etherscan.py`, `tools/adapters/trongrid.py`, tests with `respx`.
- Steps: GET-only requests: Etherscan v2 `?chainid=1&module=account&action=txlist&address=…&apikey=` and TronGrid `/v1/accounts/{addr}/transactions/trc20?limit=50` with the `TRON-PRO-API-KEY` header; both captured as `CHAIN` evidence; summary counterparties and USDT totals.
- Acceptance: the synthetic Tron address in the WhatsApp export resolves to a capture; `chain_lookup {"chain":"TRON"}` no longer returns `UNAVAILABLE`.

### P1-4 Sanctions check with an offline list
- Files: `scripts/build_ofac_list.py` (SDN XML → `data/sanctions/ofac_digital_currency.json`), `analytics/sanctions.py`, `tools/impl/surface.py` (`sanctions_check`), tests with a fixture XML.
- Acceptance: `sanctions_check` returns `{sanctioned, source:"ofac_sdn_offline", list_version}`; `assess_wallet.sanctions` populated; Chainalysis live check optional behind the key.

### P1-5 Multilingual extraction upgrades (plan 04 leftovers)
- Files: `extract/normalize.py` (script spans), `extract/translit.py` (indic-transliteration), `extract/lexicon.py` (RapidFuzz thresholds, ambiguity rule), `extract/ner.py` (GLiNER adapter behind a manifest), tests per plan 04.
- Acceptance: Devanagari and Gurmukhi variants of lexicon terms match; "safed maal" finds सफ़ेद माल through index-time expansion; NER adds LOCATION/SHIPPING_TERM spans with lower confidence; scenario 9 passes in all three scripts.

### P1-6 Monitoring triage model and report narrative
- Files: `monitor/triage.py` (blend a Sonnet relevance score when `triage_model_enabled`), `reports/narrative.py` (narrative provider using the configured harness's worker model), tests with stubs.
- Acceptance: with a key, alerts carry a one-sentence model relevance note; reports have an executive summary whose sentences all pass the claim checker.

### P1-7 Tor collector, minimal slice (only if the venue allows Tor)
- Files: `capture/tor.py` (`TorHttp`: `httpx[socks]`, `socks5h://` proxy, `.onion` hosts only, HTTP only, 25 pages per job, 6 requests per minute, image quarantine), `tools/impl/dark.py` (`onion_fetch`, `onion_lookup` via CIRCL), `policy/rules.py` (`tor` tag requires `tor_enabled` and a healthy proxy), `infra/docker-compose.yml` (profile `collector` with a `tor` service on an internal network), `api/v1/routes/health.py` (`collector` check probes `check.torproject.org` through the proxy), tests with a fake SOCKS endpoint.
- Acceptance: with the profile up and a case switch on, `onion_fetch` captures a **synthetic** test hidden service page as `OSINT_DARK` with images quarantined; with the switch off, `POLICY_DENIED`; with Tor down, `UNAVAILABLE`.

### P1-8 Digest and changes in the agent
- Expose `GET /cases/{id}/digest` as a `case_digest` tool for the Case Lead and Hermes later; acceptance: "What changed since yesterday?" cites alerts and new evidence.

---

## P2 — post-hackathon (from plan 16)

- Telegram read-only Telethon adapter (Apify is a POST API and violates the GET/HEAD invariant; keep it out).
- Username lookup through the MCP gateway and `osint-tools-mcp-server`, bound to handles already observed in the case.
- MCP gateway wiring (`DARKNETRA_MCP_GATEWAY_URL` is unused today) with `mcp-scan` in CI.
- Tavily adapter or removal of the unused `DARKNETRA_TAVILY_API_KEY` setting.
- Durable workers (`arq`), Hermes pocket agent, Codex analyst, Graphiti, guardrails, STIX export, offline packaging.

---

## Test debt to close alongside

- Scenario matrix (plan 17): rows 27 (prompt injection inside a capture), 39 (Monero reasons), 31 (alert overflow), 32 (scheduler catch-up) have no dedicated tests by keyword scan; add `tests/scenarios/` files named by row.
- Live markers: add `pytest -m live` runs for Claude/Ollama/SearXNG when credentials exist, recorded before the finale.
