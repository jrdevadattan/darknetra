# DARKNETRA readiness audit — Tuesday 8 September 2026 (hackathon day)

Scope: the built system as it runs on the team laptop at 06:00–06:50 IST. Backend branch `codex/complete-backend-gaps` (commit `3fa283f`), frontend worktree `.cache/chakra-workspace` on `codex/ai-elements-workspace` (commit `0ee9092`). Nothing was changed in code; the only state changes were test artefacts (a temporary account `ui.audit.3f09`, now deactivated and removed from cases; one diagnostics case `CHD-2026-0015` created by the backend's own live smoke script; one walkthrough run on `CHD-2026-0002`).

Companion plans written from this audit: `docs/plan/18-sandbox-setup.md` (what to configure and how to verify it), `docs/plan/19-gap-closure-plan.md` (missing features, prioritised), `docs/plan/20-ui-completion-plan.md` (UI gaps and demo polish).

---

## 1. Verdict

The product is real and demoable **in deterministic offline mode**: cases, immutable evidence, extraction, lexical retrieval, cited answers over SSE, correlation with human decisions, graph, monitoring with alerts, versioned reports, audit, private chats, and a polished Next.js workspace with an agent-activity graph. Every checkpoint of the HTTP demo walkthrough passes, 387 of 388 backend tests pass, the frontend's 17 unit tests pass, and retrieval recall@5 is 1.0 on the ten fixture questions.

What is **not** true today, and would be visible to a judge who pokes:

1. **No language model is connected.** Answers are deterministic evidence quotations (correct, cited, but not conversational). Claude, NVIDIA NIM and Ollama adapters exist; none has credentials or weights.
2. **No live web search or dark-web index works.** Inside the container, DuckDuckGo serves an HTTP 202 challenge page with no results, and Ahmia redirects `/search/?q=` to its homepage. Only RSS reads, direct page reads (Trafilatura), the Jina reader, Wayback, keyserver and mempool lookups actually return content. SearXNG is the intended search provider and requires a **public HTTPS** endpoint; the hardened fetcher rejects private addresses by design.
3. **Tor is not connected and cannot be enabled by configuration.** There is no Tor daemon, no SOCKS dependency, the fetcher rejects `.onion`, `onion_fetch` is a placeholder, and readiness reports `collector: disabled`. This is unimplemented (M9), not misconfigured.
4. **Embeddings, GNN, OCR, NER, sanctions data, ETH/TRON adapters, Telegram and identity lookups are absent.** Each returns an explicit "unavailable" rather than a fake result, which is the right behaviour, but the demo has to route around them.
5. **The UI has no Trends or Wallets panel** although both backend endpoints work, and members can only be added by pasting a user UUID.

Everything above is fixable in hours for the demo-critical items (section 7), except Tor.

---

## 2. What is running

| Component | State | Evidence |
|---|---|---|
| PostgreSQL 16 + pgvector | `darknetra-postgres-1`, healthy, 47 tables, migrations 0001–0003 | `docker ps`, `/health/ready.db = ok` |
| API (FastAPI) | `darknetra-api-1`, healthy on 127.0.0.1:8000; one process runs jobs and the scheduler | readiness `degraded` (embedding, harness), `scheduler: ok` |
| Web (Next.js 16 standalone) | `darknetra-web-1` on 127.0.0.1:3000, proxies `/api/v1` to `http://api:8000` | login works at `http://localhost:3000` |
| Settings | `demo_mode=true`, `offline_mode=true`, `harness_mode=deterministic`, `monitor_interval_override=120`, banner `SYNTHETIC DEMO` | `GET /admin/settings` |
| Models | case lead `claude-opus-5`, worker `claude-sonnet-5`, offline `qwen3:8b` configured by name; none reachable | no key, no Ollama container, no NIM URL |
| Data | 16 cases; `CHD-2026-0002` is the seeded 16-evidence demo case (355 alias, 353 price, 353 quantity, 221 substance, 9 BTC, 7 PGP observations; 11 pending candidates; 1 STRONG accepted pair at 80; 3 wallet alerts; 2 reports; 15 trend series). The other cases are Playwright/diagnostic leftovers named `SYNTHETIC interface verification …` | `/cases`, `/summary`, `/analytics/links` |

Environment gotcha: the backend's `DARKNETRA_WEB_ORIGIN` is `http://localhost:3000`. Opening the UI at `http://127.0.0.1:3000` fails login with `FORBIDDEN Origin is not permitted`. Always use `localhost`.

---

## 3. Verification run today

| Check | Result | Notes |
|---|---|---|
| `scripts/manage.py test` (ruff, mypy strict, pytest) | **387 passed, 1 failed**, 202 s | Failure: `tests/integration/test_stdio_mcp.py::test_real_sdk_stdio_handshake_calls_isolation_and_revocation` asserts a fixed tool set that lacks `robin_search`; the MCP server correctly lists 29 tools. Stale expectation, not a product defect. |
| `scripts/manage.py demo` (HTTP walkthrough) | **7/7 checkpoints passed** | inventory, retrieval, cited SSE answer, decision + confirmed graph, wallet availability, monitoring alert review, versioned report + appendix. Transcript `backend/evals/out/walkthrough-20260908T004541Z.json`. |
| `run_retrieval_eval.py` | **Recall@5 = 1.000** (10 questions) | lexical only; the script needs `--seed-result` pointing at the main checkout's `data/synthetic/out/seed_result.json` when run from the worktree |
| Frontend `npm test` | **17 passed** | CSRF, multipart, refresh, SSE framing, permissions |
| Frontend Playwright | 3 scenarios recorded passing at 05:56 today by the builder; screenshots in `frontend/test-results/` | not re-run here (needs `DARKNETRA_E2E_USERNAME/PASSWORD`) |
| Live tool probes via `POST /tools/{name}/health` | all network tools `disabled_by_mode` | expected while `offline_mode=true` |
| Live smoke inside the container (`scripts/reuse_smoke.py`, network on for that process) | see section 5 | creates and closes a diagnostics case |
| Contract vs plan 11 | **0 missing endpoints**, 15 extra (chats, plugins, digest, execution snapshot, monitor/trends) | `docs/openapi.json`, 87 paths |

---

## 4. What is not set up (and what each needs)

| Capability | Status now | What it needs | Plan |
|---|---|---|---|
| Claude harness | adapter present, `claude_agent_sdk` installed in the image; no key | `DARKNETRA_ANTHROPIC_API_KEY`, `DARKNETRA_HARNESS_MODE=auto`, `DARKNETRA_OFFLINE_MODE=false`, restart API; egress to api.anthropic.com | 18 §2 |
| Ollama (local model) | compose profile `offline` exists; container not started; no weights | start profile, `ollama pull qwen3:8b`, keep `harness_mode=auto` with `offline_mode=true` (routes to OFFLINE) or set `harness_mode=offline` | 18 §2 |
| NVIDIA NIM | adapter present; unconfigured | `DARKNETRA_NIM_BASE_URL` (…/v1), `DARKNETRA_NIM_MODEL`, prices, optional key; `harness_mode=nim` | 18 §2 |
| Dense retrieval | code present; `sentence_transformers` not installed in the image; no weights | rebuild image with `--build-arg DARKNETRA_EMBEDDINGS=1`, put a local 1024-d model dir in the `models` volume, `DARKNETRA_EMBEDDING_BACKEND=sentence_transformers`, `DARKNETRA_EMBEDDING_MODEL_PATH`, restart, `scripts/reindex.py` | 18 §3 |
| Web search | DuckDuckGo blocked (202 challenge); SearXNG unset; Tavily key setting exists but **no Tavily adapter** | public HTTPS SearXNG with JSON and `bing,brave` engines → `DARKNETRA_SURFACE_SEARCH_SEARXNG_URL` | 18 §4, 19 P0-2 |
| Dark index (Ahmia / Robin) | Ahmia answers `/search/?q=` with 302 → homepage; parser then finds no results | pre-captured fixture for the demo; adapter fix to follow Ahmia's actual search behaviour | 19 P0-3 |
| Tor / onion fetch | not implemented: no daemon, no SOCKS dep, fetcher rejects `.onion`, placeholder tool, `collector: disabled` | code (M9 slice) + `tor` container + `DARKNETRA_TOR_SOCKS_URL`; venue may block Tor | 18 §6, 19 P1-7 |
| Chain lookups | BTC via mempool.space only; ETH/TRON return `UNAVAILABLE` | Etherscan v2 / TronGrid GET adapters + keys | 19 P1-3 |
| Sanctions | placeholder; no dataset | OFAC SDN offline list builder; Chainalysis key optional | 19 P1-4 |
| GNN wallet risk | `models/` directory absent; torch not installed; ledger not imported | copy `classic_ml/models` + `predict.py` to `models/gnn/`, image with the `gnn` extra, `POST /cases/{id}/ledger/import` | 19 P1-2 |
| OCR / vision transcription | `transcribe_image` health `failed: OCR provider is not configured` | Tesseract (hin, pan) in the image or Claude vision when a key exists | 19 P1-5 |
| NER, transliteration, script tags, fuzzy lexicon | not implemented (validators + exact lexicon + novel terms exist) | plan 04 tasks T1, T5, T6 | 19 P1-6 |
| Telegram | placeholder; Apify rejected by the GET/HEAD invariant | read-only Telethon adapter (M7) | 19 P2 |
| Username lookup | placeholder, policy-bound design only | MCP gateway + osint-tools server (M7/M8) | 19 P2 |
| MCP gateway, Apify, Tavily settings | present in config, unused by any code path | wiring work; do not present as available | 19 P2 |
| Monitoring triage model, report narrative model | flags exist (`DARKNETRA_TRIAGE_MODEL_ENABLED=false`, `narrative` option) | a working harness first | 19 P1-8 |

---

## 5. How scraping works, and what happened live

Pipeline for every network tool (`tools/invoke` → `policy.engine.check` → `capture.fetcher.SafeHttp` → `capture.gate` → `evidence.ingest_bytes` → derivative → index/extract jobs → excerpt):

- **Policy** rechecks the actor's current role and case membership, denies when `offline_mode`, when the tool's source class is not in `case.source_policy.allowed_source_classes`, when a `tor`/`telegram` tag lacks its case switch, or when a person lookup is requested; then applies the per-source hourly cap.
- **Fetcher** allows GET/HEAD only, `http`/`https` on ports 80/443, no credentials in the URL, no `localhost`/`.local`/`.onion`; resolves DNS and requires **every** answer to be a public IP; pins the connection to the first IP with SNI; sends `User-Agent: DARKNETRA/0.1 read-only capture` and `Accept-Encoding: identity`; rejects compressed responses; follows at most three redirects, each re-validated; 429 → `RATE_LIMITED`, other 4xx/5xx → `UNAVAILABLE`; 10 MiB ceiling; 30 s timeout.
- **Gate** stores the exact bytes as evidence (`origin=CAPTURE` or `MONITOR`, encrypted locator, requester), writes custody and audit, queues chunking and extraction, and returns only the evidence code plus an excerpt of at most 1,200 characters. Dark-sourced images are quarantined.
- **Parsers** run only on captured bytes: DuckDuckGo results need `.result .result__a` markup, SearXNG needs JSON `results[]`, Robin's parser reads Ahmia's result page, Trafilatura extracts main text, feedparser parses feeds. Monitoring maps `web_search` → `surface_search` and `onion_search` → `robin_search` and counts only parsed entries as hits.

Live results from inside the API container today (network enabled for that process only):

| Tool | Result | Root cause |
|---|---|---|
| `rss_read` (Django weblog) | OK, 3 entries captured | — |
| `public_page_read` (docs.python.org) | OK, 2,268 characters via Trafilatura | — |
| `agent_reach_read` (r.jina.ai) | first run `NETWORK_REQUIRED`, re-run OK 17,664 characters | transient upstream; works |
| `surface_search` (DuckDuckGo) | captured page, `UNAVAILABLE: Search page contains no recognizable results` | DuckDuckGo returned HTTP **202** and a bare page (bot challenge); no `.result` markup |
| `robin_search` / `onion_search` (Ahmia) | first run `NETWORK_REQUIRED`, re-run captured 4,735 bytes = the Ahmia **homepage** | Ahmia answers `/search/?q=` with a 302 to `/` for this client (the same happens from a normal browser), so the index parser sees nothing |
| `wayback_lookup`, `keyserver_lookup`, `chain_lookup` (BTC) | not exercised live today; plain reachability of archive.org, keys.openpgp.org and mempool.space confirmed from the container | — |

Consequence: **the OSINT scouts have no working search entry point** until SearXNG (or an equivalent adapter) is configured, and the dark lane has no working index. Everything downstream of a URL (fetch, capture, extract, cite) works.

---

## 6. Tor: precise status

- Host: no process listening on 9050/9150; no Tor Browser running.
- Compose: no `tor` service or profile; `DARKNETRA_TOR_SOCKS_URL` is empty and referenced only by settings.
- Backend: no SOCKS transport dependency (`socksio`/`httpx[socks]` absent); `validate_url` rejects `.onion`; `onion_fetch` and `onion_lookup` are registered placeholders returning `UNAVAILABLE`; the policy engine has a `tor` tag that consults `case.source_policy.tor_enabled`, so the switch exists, the transport does not.
- Readiness: `collector: disabled — Isolated collector is not configured`.

To have any live onion capture, plan 19 P1-7 must land (SOCKS transport restricted to `.onion` through `socks5h://tor:9050`, an isolated `tor` container, a `tor_status` probe, image quarantine, policy switch). Even then the UIET/PEC network may block Tor; pre-captured onion snapshots remain the demo path, which is also the safer thing to put on a projector.

---

## 7. UI status

Implemented (verified by page reads, Playwright screenshots and source): login with forced password change; private workspace with provider picker (Automatic, Claude, NVIDIA NIM, Local model) and budget; case workspace with Overview (timeline), Evidence (upload with source class and custody note, filters, table, detail), Search & retrieval (hybrid/lexical/semantic, source classes), Entities, Relationships (React Flow graph, provenance), Findings & decisions (candidates, decide, promote, draft finding), Monitoring (watchlists, typed items, run-now, attempts), Alerts (ack/dismiss/escalate with rationale), Reports (packs with formats), Sharing & policy (members by UUID, source policy, plugin allowlist), Audit trail; global Tools & integrations (catalog with availability) and Settings (theme, readiness, model defaults, API tokens); case conversation with citations, "Citations checked", sources chips, and the Agent activity panel (graph, timeline, output log).

Gaps (detail in plan 20): no Trends panel; no Wallets panel (assessments exist in the backend); no digest card; no user directory for adding members; no taxonomy or users administration screens; report failures show status without a reason (backend has no error-detail endpoint); the case list shows every SYNTHETIC test case to the admin; the `127.0.0.1` origin trap.

---

## 8. Risks for the finale, ranked

1. **Judges ask a free-form question and get a quotation-only answer.** Mitigation: configure Claude (or Ollama) before the demo (plan 18 §2); keep deterministic mode as the fallback toggle.
2. **"Show me the dark web / OSINT lane" returns nothing.** Mitigation: public SearXNG today (plan 18 §4) or pre-captured fixtures; never promise Tor.
3. **Wrong origin on the demo laptop** (`127.0.0.1`). Mitigation: bookmark `http://localhost:3000`.
4. **Case clutter** in the sidebar. Mitigation: archive the `SYNTHETIC interface verification …` and diagnostics cases (UI or API), keep `CHD-2026-0002`.
5. **One failing test in CI-style runs.** Mitigation: update the expected tool set in `test_stdio_mcp.py` (plan 19 P0-6).
6. **No embeddings** means "semantic" mode silently falls back to lexical (the UI says so). Mitigation: either provision bge-m3 (plan 18 §3) or say "lexical + transliteration" plainly.
7. **Venue internet**: the OSINT lanes need egress from the Docker API container; test on the venue Wi-Fi first thing.

---

## 9. What to tell the judges honestly

Say: every fact on screen is an immutable evidence row; the AI never writes facts; Tor collection is designed (policy switch, quarantine, isolated collector) and scheduled for the next milestone; live search runs through a hardened read-only capture gate and is disabled by default. Do not say: "Robin MCP", "Tor connected", "semantic search" (unless embeddings are provisioned), or "the model found X" (the tools found X; the model cited it).
