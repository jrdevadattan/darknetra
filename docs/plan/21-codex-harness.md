# 21 — Codex (ChatGPT subscription) harness, live scraping stack, Trends & Wallets UI

Status: implemented and verified on 8 Sep 2026 (host + Docker). This plan records how the pieces fit, how to
run them, and what an operator must provide. Milestone: M7 (post-hackathon reach) pulled forward.

## 1. What changed

| Area | Change |
|---|---|
| Harness | `backend/darknetra/agent/harness_codex.py`: Codex Python SDK (`openai-codex`, bundled CLI 0.147) is a first-class harness. `harness_mode=auto` prefers a signed-in Codex, then Claude key, NIM, local model. Threads/runs/messages accept `harness="CODEX"` (migration `0004_codex_harness`). |
| Case tools | Codex reaches case evidence only through the case-bound stdio MCP server (`darknetra.tools.adapters.stdio_mcp`). Policy, capture gate, claim checker and audit are unchanged. Delegation (`delegate_task`) runs inside that server with `DelegationState(mode="CODEX")`. |
| Isolation | The app-server is launched per run with `codex -c` overrides: only the `darknetra` MCP server is enabled (plus operator-reviewed extras from `DARKNETRA_CODEX_EXTRA_MCP_SERVERS` for the Case Lead); every MCP server from the operator's global `~/.codex/config.toml`, ChatGPT apps, browser/computer use, memories, plugins, hooks, goals and Codex's own sub-agents are switched off; sandbox `read-only`, approval `never`; the shell tool is off unless `DARKNETRA_CODEX_SHELL_ENABLED=true`. |
| Secrets | The MCP child receives its case/run binding and the deployment settings through a private per-run `binding.json` (owner-only, deleted with the run's scratch directory), never on the command line. Only settings the operator actually configured are exported. |
| Activity graph | Codex-native steps are public nodes: `codex_web_search` (Globe, "Lead only"), `codex_shell` (when enabled), reasoning *summaries* as stage nodes, the "Case tool server" stage (starting/ready/failed), and every DARKNETRA tool call (transport `codex_mcp`, "Case tool" pill) with its evidence codes. Private reasoning text is never stored. |
| Private chats | `POST /chats` provider `CODEX`: tool-free Codex thread (no MCP, no web search). |
| Scraping | Surface search via self-hosted SearXNG (Compose service) with DuckDuckGo fallback that reports its bot challenge explicitly; Ahmia dark index via clearnet with automatic fallback to Ahmia's onion service through the Tor collector; `onion_fetch`/`onion_lookup` implemented over `capture/tor.py` (v3 onion only, socks5h, 10 MiB, GET/HEAD). `/health/ready` reports the Tor circuit and the harness sign-in state. |
| UI | Trends panel (daily term series with sparklines, z-score spikes, new-term candidates, "Run trend detection"), Wallets panel (sanctions, traceability, GNN score, live lookup captured as evidence), archived cases hidden by default with a toggle, `127.0.0.1` origin notice on the login page, Codex provider in the chat selector. |
| Hygiene | `backend/scripts/archive_synthetic_test_cases.py` closes and archives leftover SYNTHETIC verification cases. Tool validation errors now return the failing field names (never values) so the model can correct its arguments. |

## 2. Runtime layout

```
API process ──CodexHarness.run()──▶ codex app-server (per run, -c overrides, CODEX_HOME auth)
     │                                   │
     │  run_events (activity.updated)     │ MCP stdio: python -m darknetra.tools.adapters.stdio_mcp
     │◀──────────────────────────────────┤   binding.json → case id, run id, role, 2h case-bound token
     │                                   │   → policy check → capture gate → evidence → audit
     ▼                                   ▼
PostgreSQL (threads, runs, run_events, evidence, audit)   Codex web search (leads only)
```

Sequence per run: issue case-bound token → write `binding.json` → launch app-server → start/resume thread with
developer instructions (system prompt + Codex addendum) → stream items → map to run events → final answer with
```claims``` block → claim checker → revoke token → delete scratch.

## 3. Operator setup

Host (once):

```bash
codex login            # ChatGPT subscription; writes ~/.codex/auth.json
```

`.env` (see `.env.example`):

```
DARKNETRA_OFFLINE_MODE=false
DARKNETRA_HARNESS_MODE=auto            # or codex
DARKNETRA_CODEX_WEB_SEARCH=disabled    # case lookups use audited capture MCP
DARKNETRA_CODEX_SHELL_ENABLED=false
DARKNETRA_CODEX_AUTH_HOST=C:/Users/<you>/.codex/auth.json   # mounted read-only into the api container
DARKNETRA_SURFACE_SEARCH_SEARXNG_URL=http://searxng:8080/search
DARKNETRA_SURFACE_SEARCH_SEARXNG_ALLOW_PRIVATE=true
DARKNETRA_TOR_SOCKS_URL=socks5h://tor:9050
```

Bring everything up:

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile collector up -d --build
```

Then `GET /api/v1/health/ready` must show `harness: ok (Codex … signed in)` and `collector: ok (Tor circuit verified)`.
Dark-lane tools additionally require the case policy to allow `OSINT_DARK` and `tor_enabled=true`.

## 4. Verification record (8 Sep 2026)

- Unit: `pytest tests/unit` → 295 passed (Codex harness, selection, launch overrides, TOML rendering, Robin fallback).
- Host smoke (`CodexHarness.run` on CHD-2026-0002): Codex called `list_entities` and `search_evidence` through the MCP
  server and answered with two cited wallet claims (E-0007, E-0010, E-0011, E-0012, E-0015 / E-0007, E-0010, E-0013,
  E-0014); 21 run events and 5 `tool.call` audit rows written by the MCP child; usage 29k/765 tokens, cost 0.
- Isolation check (`codex -c … mcp list`): only `darknetra` enabled; `composio`, `exa`, `tavily`, `openaiDeveloperDocs`,
  `prompteneering`, `wapitick` disabled; apps/computer-use servers absent when the features are off.
- SearXNG from the api network: 26 results for "Tor Project" (bing + brave), no unresponsive engines.
- Tor: `check.torproject.org/api/ip` → `IsTor: true` from the collector container.
- Frontend: `npm run typecheck` clean; web image rebuilt.

## 5. Known limits

- Codex's `multi_agent_v1__*` tool names are still listed by the runtime even with the feature disabled; the developer
  instructions direct delegation through `delegate_task` so workers stay case-bound and audited.
- The GraphSAGE wallet scorer needs `--build-arg DARKNETRA_GNN=1` (torch + torch-geometric) and the model artefacts in
  `models/gnn/models/` (distributed separately; gitignored).
- DuckDuckGo HTML serves a bot challenge to datacentre egress; SearXNG is the supported surface provider.
- Ahmia clearnet redirects searches to its homepage; the onion index is used automatically when the case allows Tor.

## 6. Thinking mode, provider marks and run presentation (added 8 Sep 2026, evening)

| Area | Change |
|---|---|
| Reasoning mode | Case threads carry `reasoning_mode` (`normal` \| `thinking`, migration `0005_reasoning_mode`; `ThreadCreate`/`ThreadPatch`/`Thread`). Codex maps thinking → reasoning effort `high` (`xhigh` if configured), normal → configured effort or `medium`. The composer has a Brain toggle for new threads; conversation settings can switch an existing thread. |
| Codex commentary | Codex "commentary" messages (its running narration) become `Progress update` stage nodes in the activity graph instead of assistant messages, so the claim checker only sees the final cited answer. |
| Run budget | `DARKNETRA_RUN_TIME_LIMIT_SECONDS` (300) and `DARKNETRA_CODEX_RUN_TIME_LIMIT_SECONDS` (900); the MCP child inherits the parent deadline via the binding file and Codex is told its remaining minutes and the 40-call cap. Delegated Codex specialists get a 300 s slice (90 s for other harnesses) because they boot their own runtime and tool server. Tool validation errors now name the offending fields, and `read_evidence` bounds out-of-range windows (line numbers, `max_chars`, lower-case kinds) instead of rejecting them. |
| Activity panel | Rebuilt: layered tree graph (children centred under their agent, minimap, legend, click-to-inspect card), stats strip (agents, tool calls, evidence cited, thinking, issues), Timeline with run-relative offsets, evidence chips and sub-agent lanes, Agents tab (case lead + every delegated specialist with their tools and evidence), Output log. Thinking summaries are collapsible in the Graph tab. |
| Inline progress | While a run is active the conversation shows a live progress card (latest thought, last actions with provider marks, tool/evidence counters, link to the full panel). |
| Provider marks | `components/workspace/source-marks.tsx`: inline-SVG emblems for Bitcoin, Ethereum, TRON, Monero, Tor, Ahmia, SearXNG, DuckDuckGo, Codex, Wayback, Telegram, RSS, sanctions lists and keyservers, chosen from the tool name and summary. No external assets are loaded. |
| Motion | Node enter, live glow for running steps, failure shake, timeline slide-in, progress sweep; all disabled under `prefers-reduced-motion`. |
| Responsive | Below 1000 px the navigation becomes an overlay and the activity panel a bottom sheet; tables, starter cards and metric grids reflow at 720 px and 480 px. |

## 7. Final verification (8 Sep 2026, Docker api + web)

- `pytest tests/unit` → 298 passed; `pytest tests --ignore=tests/unit` (integration, contract, scenario) → 106 passed; ruff and mypy clean; `npm run typecheck` clean; api and web images rebuilt and healthy.
- Normal mode, "Which Bitcoin wallet addresses appear in this case?" → run DONE in 96 s, 9 case-tool calls, two verified claims citing E-0007.
- Thinking mode, same question with evidence mapping → DONE in 322 s, 40+ case-tool calls, five progress-update nodes, every address mapped to E-0007/E-0010/E-0011/E-0012/E-0015 and E-0007/E-0010/E-0013/E-0014 with line numbers, claim check ok.
- Thinking mode with delegation → DONE in 346 s; `delegate_task` completed, the Evidence analyst specialist node finished with "Specialist result verified", the first draft failed the claim check and the revision passed.

## 8. M7 — Robin MCP access repair (8 Sep 2026)

Codex discovered Robin but rejected its call before dispatch because the harness
denied prompts and the capture/audit tools correctly declared local writes. The
per-run MCP configuration now explicitly approves the registered tools for that
role, excludes disabled tools, and requires the case server to initialize. The
server still rechecks authorization, plugin/source policy, Tor and budgets on
every call. External servers do not inherit these approvals.

Related fixes cover unreachable-source error classification, shared parsed
Robin/onion search with a fallback checked against the invoking plugin, transport
deadlines, scout evidence-read access, disabled-tool enforcement, and onion
monitor input shape. Codex web search defaults to disabled so case lookups use
the capture path. Runtime MCP failures are visible in activity.

Verification after the repair:

- Full backend suite: **428 passed**, three existing warnings, using a separate
  migrated test database. Ruff, strict mypy on tools/capture/policy and OpenAPI
  consistency passed.
- Synthetic MCP integration tests cover capture/read, evidence hashing, both
  lead/scout roles, disabled tools and live revocation of Tor/plugin permissions.
- Live Codex diagnostic case **CHD-2026-0021**, run
  `1e86f8cc-3aec-43e8-8aef-4d7bf5fdba79`: `robin_search` reached the audited
  backend via `codex_mcp`. Ahmia's onion index returned **HTTP 504**, reported as
  `UNAVAILABLE`; the clearnet capture remains **E-0001**. The run ended `DONE`
  with insufficient evidence. This verifies MCP access, not a successful live
  index search. No result targets were fetched.
- The local API image was rebuilt and restarted. The diagnostic case was closed
  and its run token revoked. Existing case **CHD-2026-0016** has OSINT_DARK and
  Tor enabled, with Codex selected as the online harness.

See [the repeatable MCP checks](../../mcp-client.md), including `--codex` for
the model-to-MCP path. An external 504 must remain explicit; it is not evidence
of an empty index or of target availability.

## 8. Simplified workspace and department requests (8 Sep 2026, late)

- **Navigation**: six case sections instead of thirteen — Overview, Evidence, Findings (Findings / Entities / Relationships / Wallets tabs), Monitoring (Watchlists / Alerts / Trends), Requests, Reports, Case settings (Members & policy / Audit trail). Old links keep working through view aliases.
- **Evidence panel** (`case-evidence-view.tsx`): one "Add to case" card with Upload files / Paste text (pasted notes become hashed text files), sensible default source class, custody note and source class behind "More options"; a single search box that filters by name as you type and searches inside the evidence on Enter; status pills (All / Ready / Processing / Needs attention).
- **Chat**: the misleading "RUNNING: The run ended without completing" line is gone (it showed the empty error object during live runs).
- **Department requests** (`backend/darknetra/liaison`, `case-requests-view.tsx`): draft → sent → received → closed handoffs to the participants of an Indian online-narcotics investigation (local police/cyber cell, ANTF, NCB, telecom/ISP, platform, bank/UPI, crypto exchange, courier/postal, digital forensic lab, chemical forensic lab, FIU-IND/ED, Customs/DRI, CBI-INTERPOL, prosecutor). Each request carries subject, purpose, legal basis (prefilled: BNSS 2023 s.94, NDPS s.52A, BSA s.63, PMLA, Customs Act, MLAT), typed items (phone, IP, account, wallet, parcel, device, substance sample…) each tied to evidence codes, an outgoing reference, and the department's reply filed as case evidence. A Markdown letter can be downloaded; nothing is sent by the system. Migration `0006_department_requests`; routes under `/cases/{id}/requests` and `/departments`.
- **Sub-agents with a purpose**: delegation purposes now name the investigation stages (preservation, public lead review, communications/account links, financial trace, delivery links, lawful request preparation, case synthesis). The new `LAWFUL_REQUEST_PREP` purpose lets a specialist work out which records only an external holder can supply and draft the request through `draft_department_request` (saved as "Proposed by agent", never sent). `list_departments` gives agents the catalogue.
