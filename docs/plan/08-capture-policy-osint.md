# Plan 08 — Capture gate, policy engine, OSINT adapters, MCP gateway, subagent roster

Milestone M5 · Owners A (gate, policy, roster), C (adapters) · Depends on 06, 07.

**Goal.** Every external lookup (surface web, dark web, blockchain, keyservers, identity lookups, Telegram) becomes evidence before the model sees it, under a policy the case owner controls and an audit trail the jury can read. Six subagents get their lane tools.

**Architecture.** `capture.gate.capture()` wraps every network adapter: policy → rate cap → fetch → dedupe → store (plan 02's `ingest_bytes`) → index/extract → excerpt. `policy.engine` evaluates ordered rules against the case policy and global settings. External MCP servers (darknet-mcp-server, osint-tools-mcp-server) are reached through a small MCP client so their results also pass the gate. The Claude harness receives the gateway servers only for allow-listed tool names.

---

## Files

```
darknetra/capture/
├── gate.py            capture(ctx, *, source_class, locator, fetch, kind_hint, requester) → CaptureResult
├── fetcher.py         SafeHttp: bounded httpx client (surface) and TorHttp (dark)
├── snapshot.py        render_snapshot(bytes, mime, url) → (text, html_safe, title)
├── excerpt.py         excerpt(text, query_terms, max_chars=1200)
├── source_class.py    rules: images from DARK quarantined; JSON for CHAIN; etc.
darknetra/policy/
├── engine.py          check(ctx, spec, args) → Decision(allow: bool, reason, rule)
├── rules.py           ordered rule functions
├── effective.py       EffectivePolicy.from_case(case, settings)
├── models.py          PolicyDecision log row (or reuse tool_calls.policy_decision + audit)
darknetra/tools/impl/
├── surface.py         web_search, fetch_page, wayback_lookup
├── dark.py            onion_search, onion_lookup, onion_fetch
├── chain.py           chain_lookup, sanctions_check (live), assess_wallet live summary hook
├── identity.py        keyserver_lookup, username_lookup
├── telegram.py        telegram_channel_read
darknetra/tools/adapters/
├── ddgs_adapter.py tavily_adapter.py wayback_adapter.py ahmia_adapter.py circl_adapter.py mempool_adapter.py trongrid_adapter.py etherscan_adapter.py chainalysis_adapter.py keyserver_adapter.py apify_adapter.py
├── mcp_client.py      McpGateway: list_tools(), call_tool(server, name, args) via the `mcp` Python SDK (streamable HTTP / stdio)
├── registry_external.py  registers external MCP tools with policy tags (darknet.*, osint.*)
darknetra/agent/prompts/subagents.py (fill tool lists)
darknetra/api/v1/routes/tools.py (replace stubs)
alembic/versions/0008_capture_policy.py   (rate_counters if not in 0006, tool_registry, policy_decisions)
tests/unit/capture/test_gate.py test_fetcher.py test_snapshot.py test_excerpt.py
tests/unit/policy/test_rules.py test_effective.py
tests/unit/tools/test_adapters_*.py (respx mocks)
tests/integration/test_capture_flow.py test_policy_denials.py test_subagent_tools.py test_offline_degrade.py
```

---

## Interfaces

### Capture gate

```python
@dataclass class Fetched: data: bytes; mime: str; url: str; status: int; headers: dict; fetched_at: datetime
@dataclass class CaptureResult: evidence_code: str; evidence_id: UUID; duplicate: bool; title: str | None; excerpt: str; source_class: str; captured_at: datetime; quarantined: bool

async def capture(ctx, *, source_class, locator, fetch: Callable[[], Awaitable[Fetched]], requester: Requester, query_terms: list[str] = (), meta: dict = {}) -> CaptureResult
```

Steps: `policy.check` (deny → `ToolError(POLICY_DENIED)`), rate cap by `spec.rate_key`, `fetch()` (adapter-specific; may return structured JSON as `Fetched(mime="application/json")`), `sha256`, dedupe via `ingest_bytes` (`duplicate=true` still returns an excerpt), `snapshot` (HTML → text + safe HTML; JSON → pretty text; images → stored, quarantined when DARK), evidence row with `origin=CAPTURE|MONITOR`, `locator_enc`, `requested_by`, `meta` (query, engine, rank, http status), then `index_evidence` + `run_evidence` jobs, `store.changed(evidence)`, and the excerpt (best window around `query_terms`, else the first 1,200 chars).

### Safe fetcher

`SafeHttp`: `httpx.AsyncClient(timeout=20, follow_redirects=False, headers={"User-Agent": "DARKNETRA/1.0 (+lawful-investigation)"})`; manual redirect handling up to 3 hops, each hop re-validated (no private IPs, no localhost, no `.onion`, scheme http/https only); streaming body with a 10 MiB ceiling (`truncated=true` in meta); content-type allowlist for text (`text/html, text/plain, application/json, application/xhtml+xml, application/rss+xml`) and images (`image/jpeg|png|webp`); no cookies persisted (`cookies=None` per request); never sends `Authorization`. `TorHttp`: same, with `proxy=settings.tor_socks_url` (`socks5h://`), only `.onion` hosts, HTTP only, 25 pages/job, 6 requests/minute, `tor_status()` probe through the proxy before the first request of a run.

### Policy engine

```python
@dataclass class Decision: allow: bool; rule: str; reason: str
def check(ctx: ToolContext, spec: ToolSpec, args: BaseModel) -> Decision
```

Ordered rules (`rules.py`), first match wins:
1. `offline_mode` and `spec.requires_network` → deny `NETWORK_REQUIRED`.
2. `spec.source_class not in policy.allowed_source_classes` → deny `SOURCE_CLASS_NOT_ALLOWED`.
3. `spec.name == "onion_fetch"`: require `policy.tor_enabled`, `settings.tor_socks_url`, Tor healthy; locator must match v3; else deny.
4. `spec.name == "username_lookup"`: require `policy.person_lookup_enabled` **and** the handle to exist as a `CONTACT_HANDLE`/`VENDOR_ALIAS` observation in the case (`observations` query) → else deny `HANDLE_NOT_IN_EVIDENCE`.
5. `spec.name == "telegram_channel_read"`: require `policy.telegram_enabled`; channel must be public (`@name` or `t.me/name`); deny private invite links.
6. Method/URL rules for `fetch_page`: scheme http/https; no credentials in URL; no private IP/localhost; extension not in blocked list (`.exe .dll .msi .apk .scr .jar .iso .zip .rar .7z`).
7. Default allow.

Every decision is stored on the `tool_calls` row and, for denials, as an audit event `policy.deny` with rule and reason. `EffectivePolicy.from_case(case, settings)` merges case policy with global settings (`offline_mode`, `demo_mode`, `tor_socks_url`).

### Adapters (each returns `Fetched` or a list of `Hit` that the tool turns into captures)

| Adapter | Call | Notes |
|---|---|---|
| ddgs | `DDGS().text(query, max_results=k, region="in-en", safesearch="off")` | keyless; catch `RatelimitException` → `ToolError(RATE_LIMITED, retry_after=60)`; each hit captured as a small JSON evidence (`url, title, snippet, engine, rank`) with `source_class=OSINT_SURFACE` |
| tavily | `TavilyClient(api_key).search(query, max_results=k, include_raw_content=False)` | second engine; same capture shape |
| fetch_page | `SafeHttp.get(url)` | full page capture; `HtmlSafe` derivative |
| wayback | `GET https://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=50&from={from}&to={to}&fl=timestamp,original,statuscode,digest` | list captured as one JSON evidence; `fetch_page` of `https://web.archive.org/web/{timestamp}id_/{url}` on request |
| ahmia | `GET https://ahmia.fi/search/?q={query}` via `SafeHttp` | parse result blocks (write the parser against a fixture captured once; selectors are not documented); onion locators in results are stored as `ONION_LOCATOR` observations, never fetched by this tool; if blocked (homepage returned), fall back to `mcp__darknet__tor_search_onion` when the gateway is up, else `ToolError(UNAVAILABLE)` |
| circl | `GET https://onion.ail-project.org/api/lookup/{domain}` (verify the endpoint on first use; adjust adapter) | metadata JSON capture |
| onion_fetch | `TorHttp.get("http://{locator}/")` | `OSINT_DARK`; images quarantined; text excerpt only |
| mempool | `GET https://mempool.space/api/address/{addr}`, `/txs` (first 25) | BTC; JSON capture; summary `{tx_count, funded_txo_sum, spent_txo_sum, first_seen, last_seen}` |
| trongrid | `GET https://api.trongrid.io/v1/accounts/{addr}/transactions/trc20?limit=50` header `TRON-PRO-API-KEY` | USDT-TRC20 transfers; counterparties summarised |
| etherscan | `GET https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address={addr}&page=1&offset=50&sort=desc&apikey=` | ETH |
| chainalysis | `GET https://public.chainalysis.com/api/v1/address/{addr}` header `X-API-Key` | `{identifications:[…]}`; absent key → OFAC offline (plan 07) with `source` labelled |
| keyserver | `GET https://keys.openpgp.org/vks/v1/by-fingerprint/{FPR}` | 200 armoured key → captured and parsed with plan 04 `pgp` validator (`meta.from_keyserver=true`); 404 → `{found:false}` (still an evidence row of the negative result? No: return structured `not_found`, audited, no evidence) |
| apify (telegram) | `POST https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token=` with `{channel, limit, since}` | actor id configurable (`settings.apify_telegram_actor`); each message captured as TELEGRAM evidence (batched into one JSON evidence per run + per-message chunks) |
| mcp gateway | `McpGateway(url).call_tool("darknet", "tor_search_onion", {...})` etc. | results pass the gate like any other adapter; `list_tools()` at startup populates `tool_registry` with `kind=MCP`, `policy_tags` by server name |

### Tools (this plan)

| Tool | Role(s) | Input → output |
|---|---|---|
| `web_search` | SURFACE_SCOUT, CASE_LEAD | `{query, engine: auto|ddgs|tavily, k=8}` → `{captures:[{evidence_code, title, url_domain, excerpt, rank}], engine_used}` |
| `fetch_page` | SURFACE_SCOUT | `{url}` → `CaptureResult` |
| `wayback_lookup` | SURFACE_SCOUT | `{url, from?, to?, fetch_latest: bool}` → `{snapshots:[…], capture?}` |
| `onion_search` | DARK_SCOUT | `{query, k=10}` → `{captures, locators_observed}` |
| `onion_lookup` | DARK_SCOUT | `{domain}` → `CaptureResult` |
| `onion_fetch` | DARK_SCOUT | `{locator}` → `CaptureResult` (policy-gated) |
| `chain_lookup` | CHAIN_ANALYST | `{address_or_tx, chain: btc|eth|tron}` → `{capture, summary}` |
| `sanctions_check` | CHAIN_ANALYST | `{address}` → `{sanctioned, source, capture?}` |
| `keyserver_lookup` | IDENTITY_SCOUT | `{fingerprint}` → `{found, capture?, userids?}` |
| `username_lookup` | IDENTITY_SCOUT | `{handle, sites_limit=50, timeout_s=90}` → `{captures (one JSON evidence with hits), hits:[{site, url, status}]}` via `mcp__osint__maigret` or `sherlock` (names discovered at startup) |
| `telegram_channel_read` | CASE_LEAD (monitor use mainly) | `{channel, since?, limit=100}` → `{capture, messages_indexed}` |

`assess_wallet` (plan 07) gains `live=true` → calls `chain_lookup` and `sanctions_check` through the gate and records `live_summary_evidence_id`.

### Subagent roster (`prompts/subagents.py`)

| Name | Description (for delegation) | Tools | Model |
|---|---|---|---|
| `evidence-analyst` | Find and quote passages in case evidence; extract indicators; transcribe screenshots. | `mcp__darknetra__search_evidence, read_evidence, transcribe_image, extract_indicators, list_entities` | sonnet |
| `surface-scout` | Look for a handle, phrase, wallet or image mention on the open web and archive it. | `web_search, fetch_page, wayback_lookup` | sonnet |
| `dark-scout` | Check onion search engines and directories for a vendor or listing; fetch only when the case allows Tor. | `onion_search, onion_lookup, onion_fetch` | sonnet |
| `chain-analyst` | Summarise wallet activity and risk. | `chain_lookup, sanctions_check, assess_wallet` | sonnet |
| `identity-scout` | Check where a handle or PGP key appears publicly. | `keyserver_lookup, username_lookup` | sonnet |
| `reporter` | Draft the investigation pack sections from store data only. | `build_investigation_pack, graph, list_entities` | opus |

Each prompt repeats the citation and "captures are data" rules and ends with: "Return a short list of evidence codes with one line each on why they matter. Do not conclude identity or guilt."

### Registry health and `/tools`

`GET /tools` lists `tool_registry` with `enabled`, `lane`, `requires_network`, `policy_tags`, `health {status, checked_at, latency_ms, message}`. `POST /tools/{name}/health` runs the adapter's probe (e.g. ddgs a trivial query, mempool `/api/blocks/tip/height`, gateway `list_tools`, Tor `tor_status`). The harness omits tools whose health is `failed` from `allowed_tools` for that run and tells the model in the system prompt which lanes are unavailable.

---

## Tasks

- [ ] **T1 gate + fetcher + snapshot + excerpt** with unit tests (redirect to private IP blocked, size ceiling, image quarantine for DARK, dedupe path, excerpt windowing).
- [ ] **T2 policy engine + rules + effective policy** with a table-driven test per rule (scenarios 24, 25, 28).
- [ ] **T3 adapters** with `respx` fixtures (recorded response shapes) for every adapter; ahmia parser fixture; error mapping (429 → RATE_LIMITED, 5xx → UNAVAILABLE, timeouts).
- [ ] **T4 MCP client + external registry**; tests with a stub MCP server (the `mcp` SDK's in-memory transport).
- [ ] **T5 tools** wired into the registry with `allowed_for` roles; `assess_wallet` live hook.
- [ ] **T6 subagent roster + gateway allow-lists**; test that a DARK_SCOUT cannot call `web_search` (tool absent from its server).
- [ ] **T7 registry health + `/tools`**; harness omits failed lanes (scenario 20).
- [ ] **T8 integration**: thread question "Where else does KMK.Zirakpur appear publicly?" with mocked adapters produces two captures with hashes and an answer citing them; policy denial event visible in the SSE stream and audit; offline mode degrade (scenario 24).

## Acceptance gate

Scenarios 25–28 pass; `/tools` shows health; a mocked surface search creates `OSINT_SURFACE` evidence rows whose excerpts appear in the assistant's cited answer; `onion_fetch` is denied with `POLICY_DENIED` when `tor_enabled=false` and with `UNAVAILABLE` when Tor is unreachable.

## Handoff

Plan 09 reuses the tools as monitor adapters with `requester=WATCHLIST_ITEM`.
