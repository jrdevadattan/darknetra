# M7 — Codex collection progress and bounded execution

The screenshot was traced to CHD-2026-0019. Run
`06a92643-4fcc-415d-a9b8-a9ddbf718263` performed 30 local searches, one delegation,
an alert read and a digest read, with no external collection. The case had no
watchlists and OSINT_DARK/Tor were disabled. Both the system and citation-repair
prompts forced the exact final text “Insufficient evidence.”

## Changes

- Codex chooses useful permitted collection tools after checking stored evidence.
  Delegation is optional. A citation repair preserves supported partial findings
  and reads existing captures, rather than restarting collection.
- Each Codex turn receives the bounded application history once in a fresh runtime
  thread. Resuming a runtime and replaying the same history is no longer combined.
- MCP contexts share successful collection results, failed-attempt counters and
  empty-search progress. Dynamic local reads refresh. A case-policy change clears
  the collection cache; every call still refreshes authorization before reuse.
- Three empty local searches stop further local query variants until evidence is
  returned by another tool. Two identical failed attempts stop retrying. Atomic
  audit reservations enforce a 40-execution budget across MCP processes, lead,
  specialists and citation repair. The MCP deadline never extends its parent.
- `list_monitors`, `create_monitor` and `control_monitor` expose existing case
  services to the Codex lead. Creation is deduplicated; run/pause/resume require
  `monitor:run` plus case watchlist permission. Intervals are bounded to 30 minutes
  through seven days. Collection uses the existing scheduler, capture, backoff,
  audit and hit-deduplication paths. Confirmed findings remain human decisions.
- Server-authored collection receipts accompany unsupported answers. They report
  executed tools, failures and returned evidence counts separately from factual
  claims. The UI labels an empty claims list “No factual claims.”
- `transcribe_image` produces immutable OCR and canonical TEXT derivatives for
  stored images/scanned PDFs using local Tesseract. It preserves regions,
  confidence, language, page and line/span offsets, indexes the text, and returns
  review flags. Native PDF text is preserved. Limits: 90 seconds, configured page
  cap (default five), 2400-pixel OCR raster, bounded subprocess output and input.
  Cancellation kills and reaps the subprocess. English/Hindi/Punjabi and Poppler
  are bundled in the backend image. Transcription is explicitly invoked by the tool.

## Robin provider limitation

Live diagnostic CHD-2026-0025 reached the real MCP server and captured Ahmia's
HTTP 200 response as E-0001 (`8766c05e-9960-4224-813d-06de040ed8b3`). The content was
a JavaScript-dependent landing page, not search results. Its token was revoked
and diagnostic case closed. The parser now names this condition explicitly.
The provider's [current homepage](https://ahmia.fi/) also states that a non-JavaScript
version is unavailable. No interactive-control bypass was added. Successful MCP
dispatch must not be described as successful live search when the provider returns
this page. Codex can use another permitted source and preserve that limitation.

The follow-up provider diagnostic CHD-2026-0028 confirmed the same landing page
through Tor. OnionLand, an index listed by Robin upstream, returned a recognizable
results page. Robin now falls back to that captured index, excludes advertisements,
and returns its provider name and index evidence. It does not follow result tracking
links. Amnesia timed out and was not integrated. The diagnostic case is closed.

The surface-search default was also wrong: it selected DuckDuckGo even with a
configured SearXNG endpoint. `surface_search` now defaults to `auto`, choosing the
configured SearXNG endpoint; an explicitly selected provider remains explicit.

Per the user's follow-up request, new case policies default to Tor enabled and
include OSINT_DARK. Five open cases were checked through the application API;
CHD-2026-0026, CHD-2026-0027 and CHD-2026-0002 needed an audited policy update.
Offline mode, explicit case switches, plugin permissions and the collector gate
continue to be enforced.

## Live-run follow-up fixes

Run `1aa2f387-8d21-4e60-8a75-4252a2c084c0` collected public reporting through Codex
and exposed three further issues. The Boolean monitor expression could never
match the literal variant filter; validation now rejects operators and supports
explicit literal variants. Deployment demo mode shortened a six-hour schedule to
two minutes; it was disabled through the admin API. MCP reloads persisted scheduling
settings and reports effective intervals. The invalid monitor was paused with its
history retained, pending a valid replacement.

Citation repair replayed the original collection request and repeated status
checks. Repair now receives only a repair instruction and can access only stored
evidence search/read tools. Every assistant answer receives a server-authored
execution receipt, including persisted monitoring status and per-source outcomes.
Final model prose is reserved for cited findings.

## Validation

The full backend suite passes: **463 tests**, with three existing warnings. Ruff,
strict mypy on tools/capture/policy, and OpenAPI consistency pass. The frontend
production build and its 17 unit tests pass. The MCP integration matrix now
executes monitoring and OCR alongside all other implemented tool families against
real PostgreSQL and synthetic captured/provider data. Atomic reservation tests
race five contexts and permit only two identical executions; revocation tests
cover cached results, role/token/session changes and source-policy changes.

## Remaining integration work

The registry now contains 33 tools, 30 with implementations. `username_lookup`,
`sanctions_check` and `telegram_channel_read` remain explicit unavailable adapters.
ETH/TRON live chain adapters and optional semantic/GNN/NER assets remain separate
work. OCR has an explicit tool path; automatic ingest OCR needs further integration.
Enterprise products in the pasted catalogue still require vendor entitlements and
reviewed APIs. The earlier tool-access audit is a historical snapshot.
