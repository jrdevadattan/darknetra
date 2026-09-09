# Plan 18 — Sandbox setup: enabling providers, search, models, Tor prerequisites, live diagnostics

Post-build · Owner A · Depends on the built stack (`scripts/manage.py dev`). Every step is configuration or operation, not code, except where marked **code required**. Each step ends with a verification command and the exact expected signal.

Conventions: run from the repository root that owns the running Compose project (the worktree that built the web image also carries the same Compose file). Settings live in the private `.env`; the API reads them at start, so **restart the API after editing `.env`**: `docker compose --env-file .env -f infra/docker-compose.yml up -d api`. Runtime toggles (`demo_mode`, `offline_mode`, `monitor_interval_override`, `banner`) can also be changed live through `PATCH /api/v1/admin/settings` as an administrator.

---

## 0. Baseline and the two traps

- Start or verify: `uv run --project backend python scripts/manage.py dev` (idempotent). Check `http://127.0.0.1:8000/api/v1/health/ready` → `db: ok`, `vault: ok`, `scheduler: ok`.
- Open the UI at **`http://localhost:3000`**, never `127.0.0.1:3000` (CSRF origin check: `DARKNETRA_WEB_ORIGIN=http://localhost:3000`). Login errors that say `Origin is not permitted` mean the wrong host.
- One API process per database; the scheduler and jobs run inside it. Do not run `manage.py serve` on the host while the Docker API is up.
- Credentials: `DARKNETRA_ADMIN_PASSWORD` (user `administrator`) and `DARKNETRA_DEMO_ANALYST_PASSWORD` (user `analyst.demo`) in `.env`.

Verification: `uv run --project backend python scripts/manage.py demo` → seven `passed` lines.

---

## 1. Turn the network on (needed by every OSINT lane)

`offline_mode=true` denies every network tool with `NETWORK_REQUIRED`.

1. `PATCH /api/v1/admin/settings {"offline_mode": false}` (or `.env DARKNETRA_OFFLINE_MODE=false` + restart).
2. Per case, `PATCH /cases/{id}` with `source_policy.allowed_source_classes` including `OSINT_SURFACE`, `OSINT_DARK`, `CHAIN` (the seeded demo case allows SURFACE and CHAIN; add DARK only if you want Ahmia captures).
3. `GET /api/v1/tools` → network tools show `health.status != disabled_by_mode`; `POST /api/v1/tools/rss_read/health` probes live.

Verification (inside the container, network for that process only, creates and closes a diagnostics case):

```bash
docker exec darknetra-api-1 python scripts/reuse_smoke.py
```

Expected today: `rss_read ok`, `public_page_read ok`, `agent_reach_read ok` (may need a retry), `surface_search` and `robin_search` **not ok** until steps 4 and 5.

---

## 2. Connect a language model

Selection logic (`agent/service.py`): `harness_mode=deterministic` → quotations; `offline_mode` or `harness_mode=offline` → Ollama; `harness_mode=nim` or a chat that requests NIM → NIM; otherwise Claude when a key exists, else NIM when configured, else Ollama.

### 2a. Claude (recommended for the stage)

```
DARKNETRA_HARNESS_MODE=auto
DARKNETRA_OFFLINE_MODE=false
DARKNETRA_ANTHROPIC_API_KEY=sk-ant-…
DARKNETRA_ANTHROPIC_API_KEY_BACKUP=sk-ant-…   # second key, rate-limit insurance
DARKNETRA_CASE_LEAD_MODEL=claude-opus-5
DARKNETRA_WORKER_MODEL=claude-sonnet-5
```

Restart the API. The adapter runs the Claude Agent SDK's bundled runtime inside the container; the container must reach `api.anthropic.com`. Thread budgets default to USD 2.00; raise per thread in the UI if a demo question needs more.

Verification: `/health/ready` → `harness: ok`; in the UI, open `CHD-2026-0002`, new conversation, ask "Which seller handles could be the same operator? Explain." → an answer with `Citations checked`, sources chips, and cost > 0 in the activity footer. Keep `DARKNETRA_HARNESS_MODE=deterministic` in a second `.env` copy as the fallback.

### 2b. Ollama (offline fallback)

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile offline up -d ollama
docker exec darknetra-ollama-1 ollama pull qwen3:8b
```

Set `DARKNETRA_HARNESS_MODE=offline` (or keep `auto` with `offline_mode=true`). The API container reaches Ollama at `http://ollama:11434` (set by Compose). Expect slow first tokens on CPU; only evidence-lane tools are offered.

Verification: `/health/ready` → `harness: ok (offline)`; a case question returns a cited answer with harness `OFFLINE`.

### 2c. NVIDIA NIM

```
DARKNETRA_HARNESS_MODE=nim
DARKNETRA_NIM_BASE_URL=https://<host>/v1
DARKNETRA_NIM_MODEL=<model id>
DARKNETRA_NIM_WORKER_MODEL=<optional>
DARKNETRA_NIM_API_KEY=<if required>
DARKNETRA_NIM_INPUT_COST_PER_MILLION=0.0     # both prices required; 0 only for a free deployment
DARKNETRA_NIM_OUTPUT_COST_PER_MILLION=0.0
```

Verification as in 2a with harness `NIM`.

---

## 3. Dense retrieval (semantic and hybrid modes)

1. Rebuild the API image with the embedding extra: `docker compose --env-file .env -f infra/docker-compose.yml build --build-arg DARKNETRA_EMBEDDINGS=1 api`.
2. Download a 1024-dimensional Sentence Transformers model on the host, for example `huggingface-cli download BAAI/bge-m3 --local-dir ./models/bge-m3`, then copy it into the models volume: `docker cp ./models/bge-m3 darknetra-api-1:/app/models/cache/bge-m3`.
3. `.env`: `DARKNETRA_EMBEDDING_BACKEND=sentence_transformers`, `DARKNETRA_EMBEDDING_MODEL_PATH=/app/models/cache/bge-m3`, `DARKNETRA_EMBEDDING_DIM=1024`. Restart.
4. Reindex the demo case: `docker exec darknetra-api-1 python scripts/reindex.py --case-id <case uuid> --actor-id <administrator uuid>` (the UUIDs come from `GET /cases` and `GET /auth/me`).

Verification: `/health/ready` → `embedding: ok`; `POST /cases/{id}/search {"query":"courier from Zirakpur","mode":"semantic"}` → `dense_available: true`, `mode_used: semantic`.

---

## 4. Live web search (the only entry point for the surface lane)

DuckDuckGo's HTML endpoint serves a challenge page to the container; do not rely on it. Configure SearXNG:

1. Host SearXNG on a **public HTTPS** origin (the fetcher refuses private addresses, `http`, query strings and fragments in the endpoint). A small cloud VM with Docker works: run the official `searxng/searxng` image behind Caddy with a DNS name and Let's Encrypt; in `settings.yml` set `search.formats: [html, json]`, enable the `bing` and `brave` engines (the adapter requests `engines=bing,brave`), and `server.limiter: false` for your own client, or allow-list the demo laptop's IP.
2. `.env`: `DARKNETRA_SURFACE_SEARCH_SEARXNG_URL=https://<host>/search` (no query string). Restart.
3. In the UI, monitoring items and the surface scout now use SearXNG; the adapter appends `q`, `format=json`, `engines=bing,brave`.

Verification: `docker exec darknetra-api-1 python scripts/reuse_smoke.py --search-provider searxng` → `surface_search ok` with `result_count ≥ 1`; then a case question "Where else does KMK.Zirakpur appear publicly?" produces `OSINT_SURFACE` captures with evidence codes.

If no public SearXNG can be provisioned before the finale: pre-capture. Run the surface tools once from a network where they work, or upload saved search-result pages as `OSINT_SURFACE` evidence, and rehearse the questions in demo mode so replay serves them.

---

## 5. Dark index (Ahmia via Robin's parser)

Ahmia currently answers `/search/?q=…` with a redirect to its homepage for this client, so `robin_search` and `onion_search` return no results. **Code required** to follow Ahmia's real search behaviour (plan 19 P0-3). Until then, treat the dark lane as pre-captured: keep the fixture listings in `CHD-2026-0002` and say so.

Verification after the adapter fix: `docker exec darknetra-api-1 python scripts/reuse_smoke.py --selected robin_search` → `result_count ≥ 1`.

---

## 6. Tor prerequisites (for when plan 19 P1-7 lands; nothing to configure today)

What exists: a `tor` policy tag gated by `case.source_policy.tor_enabled`, the `DARKNETRA_TOR_SOCKS_URL` setting, and the `collector` readiness check. What is missing is the transport, the tool implementation and the container.

Sandbox procedure once the code exists:

1. Compose profile `collector`: a `tor` service (official Tor image or `dperson/torproxy`) exposing SOCKS 9050 only on the internal network; the API joins that network only when `DARKNETRA_TOR_SOCKS_URL=socks5h://tor:9050` is set.
2. Check the circuit from the API container: `curl --socks5-hostname tor:9050 https://check.torproject.org/api/ip` → `{"IsTor":true,…}`.
3. Enable per case: `PATCH /cases/{id}` `source_policy.tor_enabled=true` and add `OSINT_DARK`.
4. `POST /tools/onion_fetch/health` → `ok`; a capture of a **synthetic** onion fixture served on a test hidden service, never a real market, for the demo.

If the venue blocks Tor, obfs4 bridges in the Tor container config are the only option; do not attempt this on stage.

---

## 7. Chain, sanctions, keyserver, Wayback

- BTC works keyless via mempool.space. ETH/TRON need adapters (plan 19 P1-3) and keys: `DARKNETRA_ETHERSCAN_API_KEY`, `DARKNETRA_TRONGRID_API_KEY`.
- Sanctions needs the OFAC list builder (plan 19 P1-4); `DARKNETRA_CHAINALYSIS_API_KEY` is optional afterwards.
- Verification for the working ones: `POST /tools/chain_lookup/health`, `POST /tools/keyserver_lookup/health`, `POST /tools/wayback_lookup/health` → `ok` with latency.

---

## 8. GNN wallet risk

1. Copy `classic_ml/models/{graphsage_temporal_best.pt, graphsage_temporal_config.json, temporal_scaler.pkl, temporal_feature_names.txt}` and `classic_ml/predict.py` from the old repository into `models/gnn/` (the adapter imports `models/gnn/predict.py` and requires `torch` and `torch_geometric`).
2. Add the `gnn` extra to the image (plan 19 P1-2 adds a `DARKNETRA_GNN=1` build arg mirroring the embeddings one).
3. Import the synthetic ledger: `POST /cases/{id}/ledger/import` with `nodes.csv`, `edges.csv`, `address_map.csv` from the generator output.

Verification: `POST /cases/{id}/wallets/assess {"address":"<W1>","chain":"btc"}` → `gnn.class_` present with `threshold 0.7166…` and the F1 caveat, instead of `gnn_unavailable_reason`.

---

## 9. OCR for screenshots

Until plan 19 P1-5: `transcribe_image` health is `failed: OCR provider is not configured`. Chat screenshots are stored and hashed but not transcribed. After the plan: Tesseract with `hin` and `pan` data in the image, or Claude vision when a key is present; verification `POST /tools/transcribe_image/health` → `ok`.

---

## 10. MCP client access (works today)

Create a case-bound token (`POST /auth/tokens {"name":…, "case_id":…, "scopes":["cases:read","threads:run"]}`), then run one stdio server per case: `docker compose --env-file .env -f infra/docker-compose.yml run --rm -T --no-deps mcp` with `DARKNETRA_MCP_CASE_ID` and `DARKNETRA_MCP_API_TOKEN` in the environment. Any MCP client (Claude Code, Codex) lists 29 tools and calls them with the same policy and capture gate. Details: `docs/mcp-client.md`.

---

## 11. Frontend checks

```
cd frontend && npm ci && npm run typecheck && npm test && npm run build
DARKNETRA_E2E_USERNAME=analyst.demo DARKNETRA_E2E_PASSWORD=<from .env> PLAYWRIGHT_BASE_URL=http://localhost:3000 npm run test:e2e
```

Expected: 17 unit tests, 3 Playwright scenarios green against the Docker web service in deterministic mode.

---

## 12. Demo-day sequence (Wed 9 Sep)

1. On the venue Wi-Fi: `manage.py dev`; readiness; `docker exec darknetra-api-1 python scripts/reuse_smoke.py` to learn which lanes have egress.
2. Decide the harness: Claude if the key and egress work, else Ollama, else deterministic. Restart the API accordingly and confirm `/health/ready`.
3. Archive the leftover `SYNTHETIC interface verification …` and diagnostics cases; keep `CHD-2026-0002`.
4. Warm replay: with `demo_mode=true`, ask the six demo questions once in a fresh conversation; then reload and confirm `replayed` runs stream instantly.
5. Bookmark `http://localhost:3000`; keep the backup video and the deterministic `.env` copy.
6. Back up: `uv run --project backend python scripts/backup.py`.
