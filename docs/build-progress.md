# Backend execution record

The existing implementation plan and subsystem plans 00–17 were reviewed on 2026-09-06. This build follows their backend M0–M6 sequence; plan 15 is the separate frontend, and plan 16 records the M7–M9 roadmap.

## Decisions resolving plan conflicts

- The user's request supersedes the old laptop assumption: install Docker Desktop on WSL2 and run PostgreSQL 16 with pgvector in Compose.
- The original evidence bytes, hashes, provenance, custody, audit and decision content remain immutable. Mutable workflow status is separate from original content. Superseding decisions append a new row rather than editing a previous decision.
- Plan 11 is authoritative for public response shapes where the overview or a subsystem differs.
- The read-only external-source invariant takes precedence over the proposed Apify POST adapter. Unsupported sources return typed errors until a compliant adapter is configured.
- Models and sanctions datasets absent from the repository are reported as unavailable. Missing data must never be reported as a clean screening result or an invented prediction.
- A document cannot contain the hash of its final bytes. Reports keep the hash in metadata and a detached manifest rather than hashing a self-referential footer.
- The folder initially has no Git repository or backend source. Work starts in place on a new development branch, preserving the supplied documentation.

## Implemented backend baseline

This is a working local backend baseline across M0–M6. It does **not** satisfy every acceptance gate in those milestones. The table distinguishes the usable deterministic path from the remaining model, provider and evaluation work.

| Milestone | Implemented |
|---|---|
| M0 | Python 3.12/uv, FastAPI/Pydantic contracts, 43 PostgreSQL tables, Alembic migrations, restricted runtime database role, Docker Compose, health/metrics, cross-platform commands, OpenAPI export/compatibility checks and CI workflow. |
| M1 | Argon2 login, rotating/revocable sessions, CSRF, scoped tokens, global/case permissions, case lifecycle/membership, immutable custody/audit, content-addressed vault, bounded uploads/ZIP validation, deterministic document/chat/image parsing, authenticated 16-item synthetic seed. |
| M2 | Checksum-validated indicators, computed PGP fingerprints, encrypted contacts, multilingual taxonomy, exact raw spans and author contexts, versioned extraction, current-evidence entity views, case-isolated lexical retrieval and unavailable dense fallback. |
| M3 | Shared typed tool registry, policy checks on each call including refreshed authorization, Claude SDK/Ollama adapters, explicit deterministic quotation mode, persisted threads/messages/runs/events, SSE reconnection, budgets/cancellation, attachment/pinned-finding context, citation verification and context/state-sensitive replay. |
| M4 | Deterministic link/activity scoring, independent-signal/escrow controls, versioned candidates, human-only immutable decisions, graph/provenance, findings, bounded ledger import, wallet availability results and diversity-aware trends. |
| M5 | Audited GET/HEAD capture before tool-visible excerpts, public-address/redirect validation, bounded fetching, offline/source/rate policy gates and explicit errors for unsupported providers. Tests use synthetic HTTP fixtures. |
| M6 | Local evidence watchlists, scheduler/deduplication/triage/caps, human alert handling, retained original evidence under expiry/legal hold, immutable redacted report artifacts, HTTP walkthrough, backup/restore verification, startup recovery for interrupted runs/reports/ingestion. |

## Chat architecture

The user's Codex-style workspace direction is recorded in `reuse-integrations.md`:
case projects and case membership already exist; private normal chats and installable
plugin management still need implementation. The agent visibility increment now
supports actual bounded specialist execution through the registered `delegate_task`,
with shared budgets/cancellation and persisted activity inside the parent run.

## M3/M5 activity and delegation increment — 6 September 2026

- Added stable invocation UUIDs, parent-agent/call relationships, public phase summaries,
  tool/integration/transport metadata, evidence references and terminal activity states.
  Fetching, persistence and parsing are observed backend steps; no private reasoning
  or invented remote Robin MCP connection is exposed.
- Added typed `activity.updated` SSE events and case/thread/run-scoped `/execution`
  snapshots with graph nodes/edges, full bounded activity history, cursor, replay and
  cost-completeness metadata. Fixed a terminal commit/read race in SSE replay.
- Added a registered lead-only delegation tool: up to three sequential workers,
  no recursion, inherited policy, isolated caches, fixed worker allocations, shared
  deadline/tool caps, cancellation propagation and claim-checked worker results.
  Known worker usage is charged even after failure; missing provider usage is explicit.
- Reused the existing Claude SDK/MCP and Ollama adapters. No new orchestration framework
  or frontend dependency was installed. Root `frontend.md` documents React Flow and
  assistant-ui recommendations, alternate repos/licenses, exact contracts and UI states.
- Fresh database `darknetra_test_reuse_20260906_083208`: **337 tests passed in 168.44s**;
  Ruff clean and strict mypy clean on 26 tools/capture/policy files. Two existing
  dependency deprecation warnings remain. OpenAPI matches 77 paths; no migration added.
- Docker rebuilt and API updated. Actual HTTP synthetic run reconstructed 6 nodes,
  5 edges and 17 activity events at cursor 31; SSE resume returned no duplicate events.
  Report: `backend/evals/out/activity-http-20260906.json`. The diagnostic thread is
  closed with its history retained. Model-driven delegation was exercised with test
  harnesses against PostgreSQL; no live model credentials or model calls were used.
- Independently resumable or parallel child jobs, UI implementation, installable plugins,
  semantic RAG and isolated Tor monitoring remain separate work.

The application owns the run lifecycle; it has no LangChain or LangGraph dependency. A provider adapter receives bounded conversation context and calls the same registered tools as the other adapters. PostgreSQL records messages, tool results and SSE events; the claim checker verifies every assistant answer. Models cannot confirm findings or bypass capture/policy through built-in shell or web tools.

The running demo uses deterministic evidence quotations with zero model usage. Claude and Ollama integrations are present but have not been validated with live credentials/model weights. NVIDIA NIM would use an additional OpenAI-compatible adapter; that adapter is not part of this build.

## Verification record — 6 September 2026

- Docker Desktop 4.89.0 is installed and its Linux engine is accessible. Docker client/server both report 29.7.2. API and PostgreSQL are bound to loopback ports 8000 and 55432.
- Fresh database `darknetra_test_20260906_073841` was created and migrated through `0001_foundation` and `0002_report_completion`; no applied migration was rewritten.
- `scripts/manage.py test` passed: **203 tests, 129.31 seconds**, Ruff lint/format clean, and strict mypy clean on 20 tools/capture/policy source files. Two upstream deprecation warnings remain (PGPy `imghdr`, Starlette/AnyIO portal alias). A previous run exposed a test-isolation error from inherited environment keys; the test now explicitly clears those keys before asserting missing-key validation.
- Five additional provider-selection tests passed after removing an incorrect requirement for a global `claude` executable. The pinned SDK resolves its bundled runtime itself. Its configured-key path is now selectable without a separate CLI installation; this does not constitute a live model acceptance test.
- Docker was rebuilt with the current code. The restricted runtime role successfully created and reduced an inactive synthetic taxonomy variant group through authenticated HTTP, verifying the explicit mutable-configuration DELETE grant.
- The authenticated Docker seed created **CHD-2026-0002 with 16 SYNTHETIC evidence entries**. The previous synthetic case was archived, preserving its evidence and history. `scripts/demo_walkthrough.py` passed all seven checkpoints: inventory, retrieval, cited answer/persisted SSE, human decision/confirmed graph, honest wallet availability, monitoring/alert review, and versioned report/appendix download. Transcript: `backend/evals/out/walkthrough-20260906T073914Z.json` (generated and ignored by Git).
- Docker retrieval evaluation returned **Recall@5 1.000 over ten provided lexical fixture queries**. OpenAPI export matches the application with **76 paths**; required path/media-type contract tests passed.
- Backup `backups/darknetra-20260906T074027609657Z` was restored into a fresh rehearsal database and vault; **83 original/derivative/report blob references were rehashed successfully**. Existing targets were preserved and active API configuration was unchanged.
- The full generated 16-item fixture passed a real PostgreSQL/ASGI integration test: the planted A/A_CHAT pair is STRONG, the A/B shared-escrow decoy is WEAK, and candidates remain PENDING until human review. Scoring weights were not relaxed.
- Review found and fixed six issues: domestic phone report redaction, Claude history, chat attachments, entity visibility for unavailable evidence, expired-evidence reprocessing, and interrupted ingestion recovery. A bounded rereview found no remaining P1/P2 issues in those six paths.
- Additional regressions cover response transaction completion before audit insertion, context-sensitive replay, pinned findings, and background authorization revocation including cached tool calls.
- GitHub Actions is configured; no remote CI execution or production deployment has been performed.

## Remaining acceptance work

The M5 reuse increment adds five registered tools (28 total): Robin index search,
surface SERP search, RSS/Atom reading, Trafilatura page extraction and Agent Reach's
Jina public-web channel. Exact upstream pins/licenses are in `third_party/README.md`.
A real MCP SDK stdio server shares the registry, actor/case authorization and capture
gate. The optional Compose `mcp` service shares the API's database and vault and opens
no port; setup is documented in `mcp-client.md`.

The full fresh-database suite passed 274 tests in 198.15 seconds. Follow-up focused
regressions passed 74 focused tests covering feed stream input, Robin challenge/error
detection, and SearXNG engine restrictions. Strict mypy covers 24 tools/capture/policy files. Real Docker MCP
initialize/list/call returned 28 tools and three synthetic retrieval hits; revocation
denied the next call. API contract export still matches 76 paths.

Live benign diagnostics verified Trafilatura extraction (2,268 characters), Agent
Reach/Jina capture and RSS reading (three feed entries). DuckDuckGo was unreachable;
Ahmia's returned HTML was rejected as unrecognized rather than reported as no results.
The first RSS diagnostic URL returned 404 and was replaced by Django's valid feed.
Diagnostic cases are closed and retained with their captured evidence and audit trail.
The application remains in its original offline demo mode; live diagnostics enabled
network only within their own process and made no model calls.

An ephemeral public SearXNG check (INETOL, Bing/Brave only) returned RATE_LIMITED.
No public instance was made the deployment default. A reliable general-web search
provider remains an operational requirement; passing adapter tests is not proof of
live search availability. Agent Reach's installed CLI reports 1.5.0 as current;
cookie/login channels, Exa/mcporter and arbitrary upstream executables are not exposed
to the case agent.

- Dense embeddings/hybrid search, NER, OCR/transcription and trained GNN assets are absent. The baseline uses NullEmbedder/lexical retrieval and explicit unavailable results. It does not fabricate scores, clean sanctions screens or model inference.
- Live Claude/Ollama calls, provider quality/budget evaluations, SDK session resume, compressed long-thread summaries and NVIDIA NIM integration remain unverified or unimplemented. The provided short lexical-query evaluation is not a natural-language holdout benchmark or the planned promptfoo suite.
- Isolated Tor collection, unsupported Telegram/identity providers and sanctions-feed ingestion remain unavailable or policy-denied. Live checks used benign public software documentation, feeds and index queries, not investigative targets.
- Parsing/extraction does not cover every planned format, PDF page mapping, language/script tagging, fuzzy/transliteration matching or the full precedence pipeline.
- Verified image-to-author ownership, normalized price/unit correlation and near-duplicate family clustering are not implemented. No image ownership is inferred merely to increase a synthetic score.
- Optional model-assisted monitoring triage/report narratives are not enabled. PDF uses an installed Unicode font when available, with an escaped fallback; Markdown/HTML preserve UTF-8. Retention preserves physical originals and derivatives.
- Full scenario-matrix coverage, coverage percentage targets, large-corpus performance and production hardening are not established by the current tests. Use one API process per database because jobs/scheduling are in-process.
- Frontend implementation and M7–M9 remain separate tracks.
