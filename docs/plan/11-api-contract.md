# Plan 11 — API contract (v1)

Reference for M0 (route stubs and schemas), the frontend track (plan 15) and every later plan. `docs/openapi.json` exported from the app is the machine-readable truth; this document fixes names, shapes and semantics so that the export is stable.

Base path `/api/v1`. JSON request and response bodies; multipart only for uploads; `text/event-stream` for run events. All timestamps are ISO-8601 UTC with `Z`. IDs are UUIDs; evidence is additionally addressed by its per-case code `E-0007`.

---

## Conventions

### Errors

```json
{"error": {"code": "POLICY_DENIED", "message": "onion_fetch requires tor_enabled on this case", "detail": {"rule": "tor_switch"}, "request_id": "…"}}
```

| Code | HTTP | When |
|---|---|---|
| `UNAUTHENTICATED` | 401 | no or invalid session/token |
| `FORBIDDEN` | 403 | authenticated but not permitted |
| `POLICY_DENIED` | 403 | tool or capture blocked by case policy |
| `NOT_FOUND` | 404 | unknown **or inaccessible** resource (identical body) |
| `CONFLICT` | 409 | active run, existing decision, closed case, duplicate item |
| `VALIDATION` | 422 | schema or semantic validation |
| `RATE_LIMITED` | 429 | per-user/token or per-source cap; `detail.retry_after_seconds` |
| `BUDGET_EXCEEDED` | 402 | thread budget exhausted |
| `NETWORK_REQUIRED` | 503 | offline mode or lane unavailable |
| `UNAVAILABLE` | 503 | dependency down (Tor, gateway, model) |
| `NOT_IMPLEMENTED` | 501 | stub (M0 only) |
| `INTERNAL` | 500 | unexpected; no internals leaked |

### Pagination

Cursor-based: `?cursor=<opaque>&limit=<1..200, default 50>` → `{"items": [...], "next_cursor": "..."|null, "total": n|null}`. Ordering is stable (primary sort + id).

### Common schemas (`api/v1/schemas/common.py`)

```python
class Span(BaseModel): start: int; end: int; line: int | None = None
class EvidenceRef(BaseModel): id: UUID; code: str
class Page(BaseModel, Generic[T]): items: list[T]; next_cursor: str | None; total: int | None
class ActorRef(BaseModel): kind: Literal["USER","TOKEN","SYSTEM","MODEL"]; id: UUID | None; display: str
```

### Auth in requests

Browser: cookies (`darknetra_access`, `darknetra_refresh`, `darknetra_csrf`) + header `X-CSRF-Token` on mutations + `Origin`. Services: `Authorization: Bearer dk_…`. Every response carries `X-Request-ID`.

### Versioning

Additive changes are free. Removing a path, method, field, or enum member requires bumping the API major (`/api/v2`) or a documented deprecation period with both shapes served. CI enforces via `scripts/check_openapi_compat.py`.

---

## Auth

| Method | Path | Perm | Request | Response |
|---|---|---|---|---|
| POST | `/auth/login` | — | `{username, password}` | `UserMe` + cookies; 401 generic on failure; 423 `LOCKED` after lockout (detail.retry_after_seconds) |
| POST | `/auth/refresh` | cookie | — | `UserMe` + rotated cookies; 401 on reuse |
| POST | `/auth/logout` | session | — | 204 |
| POST | `/auth/change-password` | session | `{current_password, new_password}` | 204 |
| GET | `/auth/me` | session/token | — | `UserMe {id, username, display_name, global_role, must_change_password, case_roles: {case_id: role}, scopes: []}` |
| POST | `/auth/tokens` | ADMIN or INVESTIGATOR (own) | `{name, scopes: [..], case_id?, expires_in_days?: int}` | `{id, name, token, scopes, case_id, expires_at}` (token shown once) |
| GET | `/auth/tokens` | same | — | `Page[TokenInfo]` (no token values) |
| DELETE | `/auth/tokens/{id}` | same | — | 204 |

Scopes: `cases:read`, `evidence:write`, `threads:run`, `alerts:read`, `alerts:handle`, `monitor:run`, `reports:generate`.

---

## Cases

```python
class SourcePolicy(BaseModel):
    allowed_source_classes: list[SourceClass]
    tor_enabled: bool = False; person_lookup_enabled: bool = False; telegram_enabled: bool = False
    max_requests_per_hour: dict[str, int]      # surface, dark, chain, identity, telegram
    retention_days: int | None = None
class CaseCreate(BaseModel): title: str; scope_notes: str | None; authority_ref: str | None; source_policy: SourcePolicy | None; demo: bool = False
class Case(BaseModel): id; code; title; status: CaseStatus; scope_notes; authority_ref_present: bool; source_policy; legal_hold: bool; demo: bool; created_by: ActorRef; opened_at; closed_at; my_role: CaseRole | None
class CaseSummary(BaseModel): evidence_by_class: dict; evidence_by_status: dict; observations_by_type: dict; pending_candidates: int; open_alerts: int; active_items: int; threads: int; last_activity_at
class TimelineEntry(BaseModel): at; kind: str; title: str; ref: {type: str, id: UUID}; actor: ActorRef | None
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/cases` | CASE_CREATE | creator becomes OWNER |
| GET | `/cases` | session | visible cases; `?status&q` |
| GET | `/cases/{case_id}` | CASE_VIEW | |
| PATCH | `/cases/{case_id}` | CASE_EDIT / CASE_MANAGE_POLICY for `source_policy`, OWNER for `legal_hold` | partial update |
| POST | `/cases/{case_id}/close` `/reopen` | CASE_CLOSE | `{reason}` |
| POST | `/cases/{case_id}/archive` | CASE_ARCHIVE | irreversible |
| GET | `/cases/{case_id}/members` | CASE_VIEW | `[{user, role, added_at}]` |
| POST | `/cases/{case_id}/members` | CASE_MANAGE_MEMBERS | `{user_id, role}` |
| PATCH/DELETE | `/cases/{case_id}/members/{user_id}` | CASE_MANAGE_MEMBERS | last-owner invariant → 409 |
| GET | `/cases/{case_id}/timeline` | CASE_VIEW | `Page[TimelineEntry]`; `?kind&from&to` |
| GET | `/cases/{case_id}/summary` | CASE_VIEW | `CaseSummary` |
| POST | `/cases/{case_id}/ledger/import` | LEAD | multipart `nodes.csv, edges.csv, address_map.csv` → `{nodes, edges, addresses}` (plan 07) |

---

## Evidence

```python
class DerivativeSummary(BaseModel): id; kind: DerivativeKind; status; extractor; version; lang_tags: list[str]; script_tags: list[str]; text_len: int | None
class CustodyEvent(BaseModel): action; actor: ActorRef; at; hash_verified: bool | None; note: str | None
class Evidence(BaseModel): id; code; case_id; sha256; size_bytes; mime; kind; original_filename; source_class; origin; status; locator_display: str | None (redacted per role); captured_at; requested_by: {kind, id} | None; parent: EvidenceRef | None; warnings: list[str]; derivatives: list[DerivativeSummary]; custody: list[CustodyEvent]; meta: dict
class EvidenceIngestResult(BaseModel): evidence: Evidence; duplicate: bool; warnings: list[str]
class UploadItemError(BaseModel): filename: str; error: ErrorBody
class UploadResponse(BaseModel): results: list[EvidenceIngestResult]; errors: list[UploadItemError]
class TextDerivative(BaseModel): text: str; line_offsets: list[int]; page_map: list[tuple[int,int]] | None
class MessagesDerivative(BaseModel): platform; messages: list[Message]
class RowsDerivative(BaseModel): header: list[str]; rows: list[list[str]]; truncated: bool
class ImageMetaDerivative(BaseModel): width; height; format; exif_present: bool; phash: str; dhash: str
class Context(BaseModel): evidence: EvidenceRef; span: Span; text: str; before: str; after: str; line_no: int | None
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/cases/{case_id}/evidence` | EVIDENCE_UPLOAD | multipart `files[]` (1–50), `source_class?`, `note?` → 201 `UploadResponse` |
| GET | `/cases/{case_id}/evidence` | EVIDENCE_VIEW | `?source_class&origin&status&kind&q&parent_id&cursor&limit` → `Page[Evidence]` (derivatives/custody summarised) |
| GET | `/cases/{case_id}/evidence/{eid}` | EVIDENCE_VIEW | `eid` is UUID or code |
| GET | `/cases/{case_id}/evidence/{eid}/original` | EVIDENCE_VIEW_ORIGINAL | file stream; attachment for unsafe kinds |
| GET | `/cases/{case_id}/evidence/{eid}/derivatives/{kind}` | EVIDENCE_VIEW | `TEXT|MESSAGES|ROWS|IMAGE_META|HTML_SAFE|OCR`; `?version` |
| GET | `/cases/{case_id}/evidence/{eid}/context` | EVIDENCE_VIEW | `?start&end&pad=200` → `Context` |
| POST | `/cases/{case_id}/evidence/{eid}/verify` | EVIDENCE_VIEW | → `{hash_verified: bool}` |
| POST | `/cases/{case_id}/evidence/{eid}/release` | EVIDENCE_RELEASE_QUARANTINE | `{rationale}` |
| POST | `/cases/{case_id}/evidence/{eid}/reprocess` | EVIDENCE_UPLOAD | → `{job_id}` |

---

## Search and entities

```python
class SearchFilters(BaseModel): source_class: list[str] = []; evidence_ids: list[UUID] = []; lang: list[str] = []; from_: datetime | None = Field(None, alias="from"); to: datetime | None = None; include_quarantined: bool = False
class SearchQuery(BaseModel): query: str; mode: Literal["hybrid","lexical","semantic"] = "hybrid"; k: int = 8; filters: SearchFilters = SearchFilters()
class SearchHit(BaseModel): evidence: EvidenceRef; chunk_id: UUID; span: Span; snippet: str; score: float; source_class: str; lang: str; kind: str; matched_terms: list[str]
class SearchResult(BaseModel): hits: list[SearchHit]; mode_used: str; dense_available: bool; expansions: list[str]
class Observation(BaseModel): id; type: ObservationType; raw: str; normalized: Any; evidence: EvidenceRef; span: Span; validator: str; valid: bool; confidence: float; canonical_entity_id: UUID | None; run_id: UUID; meta: dict
class Entity(BaseModel): id; type; value: str; display: str; first_seen_at; last_seen_at; observation_count: int; sample_spans: list[{evidence: EvidenceRef, span: Span, snippet: str}]
class ExtractionRun(BaseModel): id; evidence_id: UUID | None; bundle_version: str; status; started_at; finished_at; stats: dict
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/cases/{case_id}/search` | EVIDENCE_VIEW | `SearchQuery` → `SearchResult` |
| GET | `/cases/{case_id}/entities` | EVIDENCE_VIEW | `?type&validator&min_confidence&evidence_id&q&cursor&limit` → `Page[Entity]` (ungrouped types return observations as pseudo-entities) |
| GET | `/cases/{case_id}/entities/{entity_id}` | EVIDENCE_VIEW | `Entity` + `observations: Page[Observation]` + `edges: list[GraphEdge]` |
| GET | `/cases/{case_id}/observations/{obs_id}` | EVIDENCE_VIEW | `Observation` + `context: Context` |
| POST | `/cases/{case_id}/extraction/run` | EVIDENCE_UPLOAD | `{evidence_id?}` → `ExtractionRun` |
| GET | `/cases/{case_id}/extraction/runs` | EVIDENCE_VIEW | `Page[ExtractionRun]` |
| GET/POST/PATCH | `/admin/taxonomy[/{term_id}]` | ADMIN_TAXONOMY | `TaxonomyTerm {id, canonical, type, variants:[{term, language, script, note}], active}` |

---

## Analytics

```python
class FeatureContribution(BaseModel): name; family; value: float; weight: float; contribution: float; evidence: list[EvidenceRef]; explanation: str
class LinkCandidate(BaseModel): id; subject_a: Entity; subject_b: Entity; score: int; band: Band; families: list[str]; features: list[FeatureContribution]; contradictions: list[dict]; status; version: int; supersedes_id: UUID | None; decision: Decision | None; run_id; rescored: bool
class ActivityCandidate(BaseModel): id; evidence: EvidenceRef; score: float; label; features: list[FeatureContribution]; status
class GraphNode(BaseModel): id; type; label; status; degree: int; meta: dict
class GraphEdge(BaseModel): id; source: UUID; target: UUID; type; status; score: float | None; families: list[str]; candidate_id: UUID | None; decision_id: UUID | None; first_seen_at; last_seen_at
class GraphDTO(BaseModel): nodes: list[GraphNode]; edges: list[GraphEdge]; truncated: bool; focus: UUID | None
class EdgeProvenance(BaseModel): edge: GraphEdge; evidence: list[Evidence]; candidate: LinkCandidate | None; decision: Decision | None
class WalletAssessRequest(BaseModel): address: str; chain: Literal["btc","eth","tron","xmr"] | None = None; live: bool = False
class WalletAssessment(BaseModel): id; address; chain; gnn: {prediction, class_: int, illicit_probability, licit_probability, threshold, model_version, n_nodes, caveat} | None; gnn_unavailable_reason: str | None; sanctions: {sanctioned: bool, source: str, program: str | None, entity: str | None, list_version: str} | None; live_summary: dict | None; live_summary_evidence: EvidenceRef | None; tags: list[str]; traceable: bool; assessed_at; version
class TrendPoint(BaseModel): day: date; count: int; unique_evidence_families: int; unique_aliases: int; unique_sources: int; z: float | None
class TrendSeries(BaseModel): term: str; type: str; points: list[TrendPoint]; candidate: bool; reasons: list[str]
class Trends(BaseModel): window_days: int; series: list[TrendSeries]; new_term_candidates: list[{term, frequency, diversity, score}]
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/cases/{case_id}/analytics/correlate` | THREAD_RUN | `{focus_entity_id?}` → `{run_id, candidates_created, candidates_rescored}` (sync for ≤ 5,000 pairs, else 202 job) |
| GET | `/cases/{case_id}/analytics/links` | CASE_VIEW | `?band&status&entity_id&min_score&cursor&limit` → `Page[LinkCandidate]` (features summarised; detail below) |
| GET | `/cases/{case_id}/analytics/links/{id}` | CASE_VIEW | full `LinkCandidate` |
| GET | `/cases/{case_id}/analytics/activity` | CASE_VIEW | `Page[ActivityCandidate]` |
| GET | `/cases/{case_id}/graph` | CASE_VIEW | `?focus&depth=1&include_pending=true&include_rejected=false&include_evidence=false` → `GraphDTO` |
| GET | `/cases/{case_id}/graph/edges/{edge_id}/provenance` | CASE_VIEW | `EdgeProvenance` |
| POST | `/cases/{case_id}/wallets/assess` | THREAD_RUN | `WalletAssessRequest` → `WalletAssessment` |
| GET | `/cases/{case_id}/wallets` | CASE_VIEW | `Page[WalletAssessment]` |
| GET | `/cases/{case_id}/trends` | CASE_VIEW | `?window_days=30&term` → `Trends` |

---

## Threads, runs, messages, findings, decisions

```python
class ThreadCreate(BaseModel): title: str; goal: str | None; harness: Literal["CLAUDE","OFFLINE"] | None; budget_usd: float = 2.0
class Thread(BaseModel): id; case_id; title; goal; status; harness; summary: str | None; pinned_findings: list[FindingRef]; budget_usd; spent_usd; assignee: ActorRef | None; created_by; created_at; last_message_at; active_run_id: UUID | None
class Claim(BaseModel): text: str; evidence_codes: list[str]; kind: Literal["observed","model","candidate","confirmed"]; verified: bool; reason: str | None
class Verification(BaseModel): ok: bool; unverified_count: int; revised: bool
class MessageBlock(BaseModel): type: Literal["text","step","attachment"]; text: str | None; tool: str | None; evidence: list[EvidenceRef] = []
class Message(BaseModel): id; thread_id; run_id: UUID | None; role: Literal["USER","ASSISTANT","SYSTEM","TOOL"]; blocks: list[MessageBlock]; claims: list[Claim]; verification: Verification | None; cost_usd: float | None; harness: str | None; replayed_from_run_id: UUID | None; at
class MessageCreate(BaseModel): content: str; attachments: list[str] = []      # evidence codes
class RunRef(BaseModel): run_id: UUID; thread_id: UUID; status
class Run(BaseModel): id; thread_id; status; harness; started_at; finished_at; cost_usd; error: dict | None; tool_calls: list[ToolCall]; replayed_from_run_id
class ToolCall(BaseModel): id; seq: int; tool: str; args: dict; status; policy_decision: dict | None; started_at; finished_at; duration_ms: int | None; evidence: list[EvidenceRef]; error: dict | None
class FindingCreate(BaseModel): title: str; claim: str; evidence_codes: list[str]; method: str; method_version: str | None; kind_hint: str | None; thread_id: UUID | None; source_message_id: UUID | None; claim_index: int | None
class Finding(BaseModel): id; case_id; thread_id; title; claim; kind; evidence: list[EvidenceRef]; method; method_version; confidence: float | None; status; version: int; supersedes_id; created_by; at; decision: Decision | None
class DecisionCreate(BaseModel): target_type: Literal["LINK","ACTIVITY","ALERT","FINDING"]; target_id: UUID; decision: Literal["ACCEPT","REJECT","DEFER","REQUEST_MORE_EVIDENCE"]; rationale: str; supersede: bool = False
class Decision(BaseModel): id; target_type; target_id; decision; rationale; decided_by: ActorRef; at; superseded_by: UUID | None
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/cases/{case_id}/threads` | THREAD_RUN | `ThreadCreate` → `Thread` |
| GET | `/cases/{case_id}/threads` | THREAD_VIEW | `Page[Thread]`; `?status` |
| GET/PATCH | `/cases/{case_id}/threads/{tid}` | THREAD_VIEW / THREAD_RUN | patch: title, goal, budget_usd, status, assignee_id |
| GET | `/cases/{case_id}/threads/{tid}/messages` | THREAD_VIEW | `Page[Message]` oldest first |
| POST | `/cases/{case_id}/threads/{tid}/messages` | THREAD_RUN | `MessageCreate` → 202 `RunRef`; 409 active run / closed case; 402 budget |
| GET | `/cases/{case_id}/threads/{tid}/runs/{rid}` | THREAD_VIEW | `Run` |
| GET | `/cases/{case_id}/threads/{tid}/runs/{rid}/events` | THREAD_VIEW | SSE (below) |
| POST | `/cases/{case_id}/threads/{tid}/runs/{rid}/cancel` | THREAD_RUN | 202 |
| POST | `/cases/{case_id}/threads/{tid}/pin` | THREAD_RUN | `{finding_id, pinned: bool}` |
| POST | `/cases/{case_id}/findings` | FINDING_EDIT | `FindingCreate` → `Finding` (DRAFT) |
| GET | `/cases/{case_id}/findings` | CASE_VIEW | `Page[Finding]`; `?status&kind&thread_id` |
| POST | `/cases/{case_id}/findings/{fid}/promote` | DECIDE | `{decision_id}` or `DecisionCreate` inline → `Finding` |
| POST | `/cases/{case_id}/decisions` | DECIDE | `DecisionCreate` → `Decision`; 409 with existing in `detail` |
| GET | `/cases/{case_id}/decisions` | CASE_VIEW | `Page[Decision]`; `?target_type&target_id` |

### SSE `GET …/runs/{rid}/events`

Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`. Each event:

```
id: 17
event: run.step
data: {"seq":17,"kind":"tool_call","tool":"search_evidence","status":"finished","summary":"12 hits","evidence_codes":["E-0003","E-0007"],"duration_ms":412,"at":"…"}
```

| event | data |
|---|---|
| `run.started` | `{run_id, thread_id, harness, budget_usd, replayed: bool}` |
| `run.step` | `{seq, kind: "tool_call"|"subagent", tool, agent?, status: "started"|"finished"|"denied"|"error", summary, evidence_codes[], duration_ms?, error?}` |
| `message.delta` | `{text}` |
| `message.completed` | `{message: Message}` |
| `store.changed` | `{kind: "evidence"|"observation"|"link"|"edge"|"alert"|"finding"|"wallet"|"trend"|"chunk", ids: [UUID]}` |
| `run.finished` | `{status, cost_usd, tokens_in, tokens_out}` |
| `run.error` | `{code, message}` |
| `run.cancelled` | `{}` |

Reconnect with `Last-Event-ID: 17` → events with `seq > 17` are replayed from `run_events`, then live. Heartbeat comment line `: ping` every 15 s. Stream closes after a terminal event.

---

## Watchlists, monitoring, alerts

```python
class WatchlistItem(BaseModel): id; watchlist_id; type; value; variants: list[str]; sources: list[str]; interval_seconds: int; active: bool; last_run_at; next_run_at; state: dict; note
class MonitorRun(BaseModel): id; item_id; started_at; finished_at; status; sources_run: dict; new_hits: int; errors: dict
class MonitorHit(BaseModel): id; item_id; evidence: EvidenceRef | None; url_display: str | None; relevance: float; alertable: bool; reasons: list[str]; alert_id: UUID | None; at
class Alert(BaseModel): id; case_id; kind; title; summary; evidence: list[EvidenceRef]; item_id; diversity: dict; config_version: str; status; finding_id; assigned_to; at; handled_at; decision: Decision | None
class Changes(BaseModel): since: datetime; evidence: {count: int, codes: list[str]}; hits: int; alerts: list[Alert]; decisions: list[Decision]; candidates_rescored: int; findings: list[FindingRef]
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST/GET | `/cases/{case_id}/watchlists` | WATCHLIST_MANAGE / CASE_VIEW | `{name}` |
| POST/GET | `/cases/{case_id}/watchlists/{wid}/items` | WATCHLIST_MANAGE / CASE_VIEW | `WatchlistItemIn` → `WatchlistItem`; 422 on invalid value |
| PATCH/DELETE | `/cases/{case_id}/watchlists/{wid}/items/{iid}` | WATCHLIST_MANAGE | delete deactivates when hits exist |
| POST | `/cases/{case_id}/watchlists/{wid}/items/{iid}/run` | WATCHLIST_MANAGE | → `MonitorRun`; 429 when capped |
| GET | `/cases/{case_id}/monitor/runs` `/monitor/hits` | CASE_VIEW | `?item_id&alertable` |
| GET | `/cases/{case_id}/alerts` | CASE_VIEW | `?status&kind&item_id` → `Page[Alert]` |
| POST | `/cases/{case_id}/alerts/{aid}/ack` `/dismiss` `/escalate` | ALERT_HANDLE | `{rationale}`; escalate → `{alert, finding}` |
| GET | `/cases/{case_id}/changes` | CASE_VIEW | `?since=` → `Changes` |

---

## Reports

```python
class ReportRequest(BaseModel): sections: list[str] | None = None; redact: bool = True; include_appendix: bool = True; narrative: bool = True; window: {from, to} | None = None
class Report(BaseModel): id; case_id; version: int; evidence: EvidenceRef; sha256: str; generated_by; at; includes: dict; claim_check: {claims: int, unverified_dropped: int, dropped: list[str]}; redaction: dict; status
```

| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/cases/{case_id}/reports` | REPORT_GENERATE | `ReportRequest` → 202 `{report_id, job_id}` |
| GET | `/cases/{case_id}/reports` `/reports/{rid}` | CASE_VIEW | |
| GET | `/cases/{case_id}/reports/{rid}/download` | REPORT_GENERATE (redacted) / EXPORT (unredacted) | `?format=md|html` |

---

## Tools, audit, admin, health

```python
class ToolInfo(BaseModel): name; kind: Literal["INTERNAL","MCP","API","CLI"]; server: str | None; lane; requires_network: bool; source_class: str | None; policy_tags: list[str]; rate_cap_per_hour: int | None; enabled: bool; health: {status: Literal["ok","degraded","failed","unknown","disabled_by_mode"], checked_at, latency_ms, message}
class AuditEvent(BaseModel): id; at; actor: ActorRef; case_id; thread_id; action; target_type; target_id; detail: dict; result_hash: str | None; request_id
class Settings(BaseModel): demo_mode: bool; offline_mode: bool; monitor_interval_override: int | None; banner: str | None; embedding_model: str; case_lead_model: str; worker_model: str; offline_model: str
class Health(BaseModel): status: Literal["ok","degraded"]; version: str; checks: dict[str, {status, message}]
```

| Method | Path | Perm |
|---|---|---|
| GET | `/tools` | session |
| POST | `/tools/{name}/health` | TOOLS_HEALTH |
| GET | `/cases/{case_id}/audit` | AUDIT_VIEW_CASE (`?action&actor_id&from&to`) |
| GET | `/audit` | AUDIT_VIEW_GLOBAL |
| GET/PATCH | `/admin/settings` | ADMIN_SETTINGS |
| GET | `/users` · POST `/users` · PATCH `/users/{id}` | ADMIN_USERS (`{username, display_name, global_role, is_active}`) |
| GET | `/health/live` `/health/ready` | — |
