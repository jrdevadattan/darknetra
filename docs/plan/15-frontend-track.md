# Plan 15 — Frontend track (separate project, consumes the contract)

Parallel from M0 · Owner D · Depends on plan 11 (`docs/openapi.json`) and the SSE protocol. Built and tested against mocks first, integrated with the running backend from Tuesday H+4.

**Goal.** The case workspace: a chat pane with a step log and citation chips, and panels that render store rows fetched from the API. Nothing on a panel comes from model prose.

---

## Stack

Next.js 16 (App Router), React 19, TypeScript 5.9, Tailwind 4, shadcn-derived primitives (reuse the investigator shell from `jrdevadattan/darknetra` if convenient), TanStack Query 5, `openapi-typescript` + `openapi-fetch` for a typed client generated from `docs/openapi.json`, MSW for mocks generated from the OpenAPI examples, Cytoscape.js for the graph, Recharts for trends, Vitest + Testing Library, Playwright for E2E.

Environment: `NEXT_PUBLIC_DARKNETRA_API_BASE_URL` (browser) and `DARKNETRA_API_BASE_URL` (server); cookies are same-site so the Next dev server proxies `/api` to the backend in development (`next.config` rewrites) to keep one origin.

---

## Routes and panels → endpoints

| Route | Panel | Endpoints | Events |
|---|---|---|---|
| `/auth/login`, `/auth/change-password` | session | `/auth/*` | — |
| `/cases` | case list, create | `GET/POST /cases` | — |
| `/cases/[id]` | overview | `/summary`, `/timeline`, `/changes?since` | `store.changed` |
| `/cases/[id]/evidence` | table, detail drawer, span viewer | `/evidence`, `/evidence/{eid}`, `/derivatives/{kind}`, `/context`, `/verify`, `/release`, upload dropzone → `POST /evidence` | `store.changed(evidence)` |
| `/cases/[id]/entities` | grouped table, observation context | `/entities`, `/entities/{id}`, `/observations/{id}` | `store.changed(observation)` |
| `/cases/[id]/graph` | Cytoscape canvas, provenance drawer, legend (pending dashed, confirmed solid) | `/graph`, `/graph/edges/{id}/provenance`, `POST /decisions` | `store.changed(edge|link)` |
| `/cases/[id]/threads` and `/threads/[tid]` | thread list; chat with step chips, deltas, claims with chips linking to `/context` | `/threads`, `/messages`, SSE `/runs/{rid}/events`, `/cancel`, `/pin` | all run events |
| `/cases/[id]/findings` | candidates and findings, decision dialog with rationale | `/analytics/links`, `/analytics/links/{id}`, `/findings`, `/decisions` | `store.changed(link|finding)` |
| `/cases/[id]/watchlists` | items CRUD, run-now, run history | `/watchlists/*`, `/monitor/runs`, `/monitor/hits` | `store.changed(alert)` |
| `/cases/[id]/alerts` | list, ack/dismiss/escalate | `/alerts/*` | `store.changed(alert)` |
| `/cases/[id]/trends` | series chart, new-term candidates | `/trends` | `store.changed(trend)` |
| `/cases/[id]/wallets` | assessments, assess form | `/wallets`, `/wallets/assess` | `store.changed(wallet)` |
| `/cases/[id]/reports` | generate, versions, download | `/reports/*` | — |
| `/tools` | registry health | `/tools`, `/tools/{name}/health` | — |
| `/audit` | audit table | `/cases/{id}/audit`, `/audit` | — |
| `/admin/*` | users, settings (demo/offline toggles), taxonomy | `/users`, `/admin/settings`, `/admin/taxonomy` | — |

Global: `SYNTHETIC DEMO` banner when `settings.demo_mode` or `case.demo`; `OFFLINE` badge when `settings.offline_mode`; backend-unavailable state on `/health/ready` failure.

---

## SSE hook

`useRunEvents(caseId, threadId, runId)`: `EventSource` with `withCredentials`; reconnects with `Last-Event-ID`; reduces events into `{steps[], deltaText, message, status, cost}`; on `store.changed` invalidates the matching TanStack queries (`['evidence', caseId]`, `['links', caseId]`, …); closes on terminal events. Pending run in another tab: `Thread.active_run_id` lets the page attach to the stream.

Chat rendering: user bubble; step chips (`tool · summary · n evidence`) in order; streamed text; final message with claims: each claim renders its evidence chips; a chip opens the context drawer via `/context` with the span highlighted; unverified claims show a warning pill; `replayed` runs show a small "replay" tag in demo mode.

Decision dialog: accept/reject/defer with rationale (min 10 chars); 409 shows the existing decision and offers supersede for LEAD/OWNER.

---

## Client invariants

- Panels read only from API responses; never parse the chat text for data.
- Every mutation sends `X-CSRF-Token` from the `darknetra_csrf` cookie.
- Unknown and inaccessible cases render the same "Case unavailable" state.
- Locators and phones render as the API returns them (already redacted per role); the UI never reveals more than the payload.
- Links inside `HtmlSafe` previews are inert; the preview iframe is sandboxed.

---

## Milestones (aligned to the backend)

| | When | Deliverable |
|---|---|---|
| F0 | Mon 7 Sep | project scaffold, generated client from `docs/openapi.json`, MSW mocks, auth screens, case list, shell |
| F1 | Mon 7 Sep | evidence panel with upload, detail, span viewer against mocks |
| F2 | Tue H+0–4 | threads: chat, SSE hook, step chips, claims → context drawer (mock SSE) |
| F3 | H+4–8 | integrate with the live backend; entities panel |
| F4 | H+8–12 | findings + decisions, graph with provenance drawer |
| F5 | H+12–16 | wallets, trends, watchlists, alerts |
| F6 | H+16–20 | reports, tools health, admin toggles, banners; polish; E2E of the demo flow |

Tests: Vitest for reducers and components; Playwright E2E `demo-flow.spec.ts` running against the backend with `--fake-harness` (same script as `demo_walkthrough.py`, driven through the UI).

Later (plan 16): CopilotKit/AG-UI adapter over the SSE stream; LibreChat as a chat-only front-end for analysts.
