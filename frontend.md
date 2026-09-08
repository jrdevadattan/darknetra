# DARKNETRA — AI Elements workspace

The frontend in `frontend/` was rebuilt with the official [AI Elements](https://elements.ai-sdk.dev/docs) registry components, React 19, Next.js 16, shadcn/Radix primitives, and Tailwind 4. It replaces the previous Chakra frontend. This document describes the implemented interface and the backend contract it uses.

## Interface

The graphite-and-sage workspace includes dark, light, and system themes with locally bundled Geist fonts. The sidebar separates shared cases and private chats. Case conversations have a collapsible activity panel with graph, chronological timeline, and recorded terminal output. Mobile navigation and activity drawers preserve access on narrow screens.

| Area | Implemented operations |
|---|---|
| Account | Cookie login, required password change, session refresh, logout, scoped API token creation/revocation |
| Cases | Create investigation or explicitly SYNTHETIC training case; scope and authority reference; case navigation |
| Case conversation | Create/send/read; citations and verification; captured evidence attachments; title, goal, status, budget; actual harness label |
| Private chat | Owner-only conversations, provider selection, title/status/budget editing, persistent messages, cancellation |
| Runtime choices | Automatic, Claude, NVIDIA NIM, and local model. The stored runtime shows any server override. Deterministic case quotation is not offered for private chat. |
| Agent activity | Official Agent, Tool, Reasoning, Terminal, and Canvas components; actual saved nodes/edges, status, phase, transport, duration, errors, cached results, and evidence references |
| Evidence | Filters, pagination, multi-file upload, immutable metadata, text/context, derivative status, custody, hash verification, authorised original download |
| Retrieval | Lexical/hybrid/semantic selection, source-class filters, returned spans/citations, explicit lexical fallback and dense availability |
| Case analysis | Entities, read-only relationship graph and edge provenance, findings, candidate decisions and promotion with a human rationale |
| Monitoring | Watchlists, typed items/source choices, run-now, pause/resume, attempt polling and errors/backoff |
| Alerts | Rationale-based acknowledgement, dismissal, escalation |
| Reports | Section/redaction/narrative/appendix choices; generation status; MD, HTML, PDF, ZIP, SHA-256 and manifest downloads |
| Sharing and policy | Authenticated case members and roles; source classes, limits, reviewed plugin allowlist |
| Integrations | Reviewed plugin catalog, actual availability, administrator enable/disable with manifest hash, searchable tool schemas/metadata |
| Settings | Theme, service readiness, administrator model defaults, offline/demo settings |

The execution graph describes agents and tool calls. The separate Relationships view describes evidence-supported case relationships. Both graphs are read-only; their nodes and edges come from the backend.

## Data and authentication

`docs/openapi.json` is the contract. `npm ci`, `npm run typecheck`, and `npm run build` generate local TypeScript declarations through `openapi-typescript`; generated declarations are not committed.

All browser requests use the same-origin `/api/v1` proxy route. `DARKNETRA_API_BASE_URL` selects one server-side backend origin at runtime and is never a browser environment variable. The proxy preserves separate session/refresh/CSRF cookies, multipart bodies, streaming responses, request IDs, and download headers. The client sends CSRF tokens on mutations and coalesces concurrent refreshes. Case query keys include the case ID; switching conversations unmounts and aborts their streams. Backend permissions remain authoritative, including indistinguishable 404 responses for unknown/inaccessible cases.

The browser content policy restricts network requests to this application. Assistant markdown uses the official MessageResponse component with external links/images disabled. Finding claims render as plain text. Evidence originals download as files; the browser does not fetch a live source directly.

## Durable run events

Case run paths are relative to `/api/v1/cases/{case_id}/threads/{thread_id}`:

1. POST `/messages` returns a run ID.
2. GET `/runs/{run_id}/execution` returns an atomic snapshot with `cursor`, `run_status`, `nodes`, `edges`, `events`, costs, and a truncation flag.
3. Fetch `/runs/{run_id}/events` with `Last-Event-ID: cursor`. The parser handles LF/CRLF framing, arbitrary chunk boundaries, comments, and multiple events.
4. Merge `activity.updated` by stable ID and sequence. `message.completed` refetches saved messages; `store.changed` invalidates case resources.
5. Reconnect with bounded backoff and a fresh snapshot. Polling independently reconciles terminal messages when the event connection is lost.
6. Cancellation targets the current run even when the activity panel inspects an older run. Server status determines when execution has ended.

Activity states are `queued`, `running`, `completed`, `failed`, `denied`, `cancelled`, and `interrupted`. Fields include parent, agent role, tool/integration identity, actual transport, phase, public summary, duration, cache flag, errors and evidence codes/IDs. Missing stages are not invented. Snapshots contain at most 10,000 events and display truncation explicitly. `terminal_inferred` identifies completion inferred from an ended run.

The Reasoning component displays **public operational summaries**. It does not request, persist, or display private chain-of-thought. The Terminal component displays the **recorded run log**; it is not a shell. HTTP providers return complete answers, so the UI waits for persisted final responses instead of simulating token streaming.

Private chats use the equivalent `/chats/{chat_id}` message/run/cancel endpoints and show verification as `NOT_APPLICABLE`; they have no case evidence, research tools, or subagent graph.

## Tool and provider semantics

The lead agent sees the audited tool registry and can delegate to bounded specialists. The current backend permits one delegation level and at most three specialists per root run, with one active specialist at a time. Children are recorded under the root run; they are not independently resumable jobs.

The Claude adapter exposes registry tools through the DARKNETRA SDK MCP server; a case-bound standalone MCP adapter also exists. Tool catalog entries describe supported transports. An activity shows MCP only when its recorded transport says MCP. Robin is an attributed local adapter using captured public search-index results; the frontend does not claim that a separate Robin MCP server exists.

Installed, enabled, configured, running, denied and unavailable are distinct. A catalog entry does not grant authority to use a tool. Global plugin disable and case source policy are enforced by the backend. Case plugin policy preserves the distinction between inherited catalog (`null`), none (`[]`), and an explicit reviewed-ID list.

Claude/NIM credentials, local model weights, search-provider keys, and an isolated Tor collector require server configuration. Selecting a provider does not provision it. Deterministic local checks do not verify paid providers or live Tor. Subscription login is not a substitute for the provider credentials configured on this server. Incomplete provider cost records are labelled partial.

## Libraries reused

| Project | Use |
|---|---|
| [Vercel AI Elements](https://github.com/vercel/ai-elements) | Official copy-in Message, Conversation, Prompt Input, Agent, Tool, Reasoning, Terminal, Canvas, Sources components |
| [shadcn/ui](https://github.com/shadcn-ui/ui) | Accessible Radix-based controls, dialogs, tooltips, forms and disclosure primitives |
| [React Flow](https://github.com/xyflow/xyflow) | Execution and case relationship graphs with editing/deletion disabled |
| [TanStack Query](https://github.com/TanStack/query) | Case-scoped queries, cursor pagination and invalidation |

Upstream component licenses and local adaptations are recorded in `frontend/THIRD_PARTY_NOTICES.md`. This uses AI Elements for presentation while retaining the Python execution protocol; it does not claim AI SDK `useChat` or AG-UI wire compatibility. No second model execution service is introduced in Next.js.

## Running and validation

See `frontend/README.md` for local and Docker commands and the reproducible test procedure. Docker builds with `npm ci`, regenerates types, compiles the standalone Next.js server, and runs it as a non-root user. Compose connects the web service to the existing API and binds the interface to loopback port 3000. CI/CD remains confined to the production branch.

Verified on 8 September 2026: TypeScript checks, 17 unit tests, three Playwright browser scenarios against the Docker web service, and the standalone Docker production build pass. `npm audit` reports zero known vulnerabilities for the locked dependency graph at verification time.

Unit coverage exercises CSRF, multipart requests, session refresh, stable errors, permissions, and chunked SSE framing. Browser checks exercise real local authentication, private conversation persistence and provider-unavailable errors, evidence upload/integrity, lexical retrieval, a deterministic case response with verified citations, activity persistence, case view navigation, themes, and mobile layout using explicitly SYNTHETIC records. They also verify access-cookie refresh, lost-session logout, and preservation of the workspace during an injected temporary refresh outage. Those immutable test records are retained.

Claude/NIM/local-model generation, live external searches, and live MCP/subagent execution were not available in this local test configuration. Graph and log checks use real recorded deterministic case-tool execution. Browser navigation checks do not imply every case mutation or report export format was exercised end to end.

## Remaining backend limits

- Live provider/collector operation depends on configured credentials, models, network and case authority. The local interface cannot manufacture that readiness.
- Report jobs have no separate status/error-detail endpoint. The UI polls report records and can show an ERROR status without an unavailable failure explanation.
- Adding case members requires an existing user's exact UUID; the API has no case-scoped directory search.
- External plugin installation, arbitrary shell commands, independent resumable workers, and production Tor deployment are outside the current backend contract.
- Graph layout is computed in the browser because the backend returns relationships, not positions. Monitoring attempts are polled separately from chat activity events.

For backend activation requirements and the remaining roadmap, see `docs/backend-audit.md` and `docs/implementation-plan.md`.
