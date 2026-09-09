# M7 — tool access and integration audit

Historical snapshot. Subsequent orchestration, monitoring and OCR changes are
recorded in [Codex collection progress](2026-09-08-codex-collection.md).

Audited 8 September 2026. The registry contains **30 tools: 26 implemented and
four explicit placeholders**. Codex supplies reasoning. The tools run inside the
case-bound MCP server, using their own capture, authorization and audit paths.
This inventory distinguishes implemented capabilities from products named in the
supplied broad forensic-tool list.

## Repairs

- Codex run tokens now include the scopes required by their role's registered
  tools: alerts/digests need `alerts:read`, and redacted packs need
  `reports:generate`. Previously these tools were discoverable but denied at
  invocation. Parent-token scopes are intersected, never expanded.
- Web search and monitoring preserve the selected tool/plugin identity when
  invoking shared search implementations. Enabling one plugin no longer requires
  enabling a different search plugin as an accidental dependency.
- MCP deadlines now outlive the registered tool deadlines, including delegation.
- `list_tool_status` reports role/case/run restrictions, token scopes and missing
  prerequisites locally. Placeholder tools remain visible there and in `/tools`
  but are omitted from the callable model catalogue. Health checks respect
  disabled plugins and missing Tor configuration.
- Chain lookup validates an address against its declared chain before any fetch.
- Public and onion transports support gzip/deflate with independent 10 MiB
  limits on received and decoded bytes. Truncated, malformed, trailing and
  unsupported encodings fail explicitly. Captured data is the decoded HTTP entity;
  encoding headers are retained. DNS pinning, redirects, GET/HEAD restrictions,
  case gates and immutable capture remain in place.

## Implemented tools

All 25 tools below that do not require an active delegation context execute in
the MCP integration matrix against real PostgreSQL, capture, parsers, services
and audit. External response bodies in that test are labelled SYNTHETIC; no live
target collection occurs. Delegation has separate run/scenario coverage.

| Capability | Registered tools | Prerequisites and limits |
|---|---|---|
| Tool status | `list_tool_status` | Case read/run permission; reports operational status, not evidence facts. |
| Evidence | `search_evidence`, `read_evidence`, `list_entities`, `extract_indicators` | Accessible case evidence and derivatives. Semantic retrieval additionally needs local embedding assets. |
| Analysis | `correlate_entities`, `graph`, `assess_wallet`, `detect_trends` | Case data; deterministic results remain candidates. GNN and sanctions sub-results require optional assets. |
| Alerts/reports | `list_alerts`, `changes_since`, `build_investigation_pack` | Required token scopes plus case permissions. MCP report generation is redacted; unrestricted exports remain subject to separate human permissions. |
| Specialist work | `delegate_task` | Active lead run, role-specific tools and bounded worker budget; no recursive delegation. |
| Search | `web_search`, `surface_search` | OSINT_SURFACE and an accessible public provider; local SearXNG is configured. Search hits are captured index observations. |
| Pages/feeds | `fetch_page`, `public_page_read`, `rss_read` | OSINT_SURFACE; HTTP capture, Trafilatura and feedparser installed. |
| Agent Reach | `agent_reach_read` | OSINT_SURFACE and reachable Jina Reader; requested URL is disclosed to Jina. Only the reviewed public-web channel is integrated. |
| Archive/key/chain | `wayback_lookup`, `keyserver_lookup`, `chain_lookup` | Appropriate source class and reachable provider. Chain lookup implements BTC/mempool.space only. |
| Dark index | `robin_search`, `onion_search` | OSINT_DARK and the corresponding plugin. Tor fallback additionally needs the collector and case switch. |
| Onion capture | `onion_fetch`, `onion_lookup` | OSINT_DARK, Tor collector and case switch; bounded GET/HEAD access. |

## Deployed checks

- Final full backend suite: **453 passed**, with three existing dependency/fixture
  warnings. Ruff, strict mypy on tools/capture/policy and OpenAPI consistency passed.
  The isolated test database used the repository migration/grants script.
- The current case **CHD-2026-0016** exposes **26 tools** through MCP. Its local
  status check reports 25 callable tools in a standalone session; delegation
  requires an active lead run. The four placeholders remain explicit. The
  diagnostic token was revoked without changing case policy.
- **CHD-2026-0022**, Codex run `c6ae9b22-949a-47aa-8057-94c58c485051`:
  tool status, alerts, digest and redacted report all completed via `codex_mcp`.
  Report evidence: **E-0002**. The case used synthetic text only.
- **CHD-2026-0023**: live web search returned two hits (**E-0001**), public page
  capture succeeded (**E-0002**), Agent Reach succeeded (**E-0003**), and Wayback
  succeeded (**E-0004**). The first article attempt exposed the compression issue;
  the initial RSS probe URL returned 404.
- **CHD-2026-0024** after the decoding repair: Python's public About page was
  captured and extracted (**E-0001**, 967 text characters), and the Python blog
  Atom feed returned two entries (**E-0002**). Both captures were readable through
  MCP `read_evidence`. Diagnostic credentials were revoked and cases closed.
- Earlier Robin/Codex verification reached the audited backend, but Ahmia's onion
  provider returned HTTP 504. That source availability limitation remains.

## Requirements that remain unmet

These capabilities are **not integrated or activated by this change**. Adding an
API key alone does not implement a missing adapter.

| Capability | Actual missing requirement |
|---|---|
| `transcribe_image` | A local OCR provider and derivative-producing implementation. Existing image ingestion provides metadata/hashes, not transcription. |
| `username_lookup` | An observation-bound, reviewed identity adapter. Broad account enumeration is not part of the implemented tool path. |
| `sanctions_check` | A verified, versioned sanctions source and a compliant captured adapter. Missing data must never be reported as “not sanctioned.” |
| `telegram_channel_read` | A compliant public GET collector or supplied exports. The proposed Apify POST collector is incompatible with this project's source contract. |
| ETH/TRON live lookup | Chain-specific adapters; relevant configured credentials where required. Current `chain_lookup` is BTC only. |
| Semantic retrieval / GNN / NER | Optional packages and reviewed local model assets. The deployed image has lexical retrieval and deterministic extraction/analysis; these optional model packages/assets are absent. |
| Tavily, Chainalysis, Etherscan, TronGrid, Apify and an external MCP gateway | Credentials/endpoints are absent in the deployment; several corresponding adapters are also absent. |

## Mapping the supplied product list

The supplied list is a broad catalogue, not an installation manifest. The existing
project covers capture, case management, graph analysis, evidence import, reports,
and passive public-source lookup with its own implementations. That does not mean
Maltego, i2, Palantir, ExifTool, Wireshark or any other named product is installed.

- **Enterprise intelligence and crypto suites** (Flashpoint, DarkOwl, Recorded
  Future, Chainalysis Reactor, Elliptic, TRM and similar): need vendor entitlements,
  documented read APIs and a reviewed capture adapter.
- **Forensic desktop suites and log tools** (EnCase, FTK, AXIOM, Autopsy,
  Wireshark/Zeek, Volatility, Ghidra): can contribute supported exported evidence;
  native acquisition/project-file adapters and those applications are not bundled.
  Existing supported text, JSON, CSV, PDF, office and chat imports remain available.
- **Additional OSINT frameworks/search indexes**: need individual bounded adapters
  and source review; no arbitrary CLI/framework execution is exposed through MCP.
- **Device acquisition, interception, cracking, active scanners and hardware**:
  are outside this case workspace's implemented read-only tool contract.

The current case retains its source policy. Unsupported integrations and missing
credentials are reported explicitly rather than represented as working tools.
