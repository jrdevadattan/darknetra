# Plan 09 — Watchlists, monitoring scheduler, dedupe, triage, alerts

Milestone M6 · Owner C · Depends on 08.

**Goal.** Investigators register what to watch (phrases in three scripts, handles, wallets, fingerprints, onion domains, channels, image hashes); a scheduler runs the same gated tools on a clock; new hits become evidence; triage decides which deserve an alert; alerts move through a lifecycle and can be escalated into findings. "What changed since yesterday?" answers from the store.

**Architecture.** `monitor/scheduler` (APScheduler) holds one job per active item; `monitor/runner.run_item()` executes adapters through the capture gate with `requester=WATCHLIST_ITEM`; `dedupe` and `triage` are pure functions; `alerts.service` owns the lifecycle and rate cap. Trend candidates from plan 07 become `TREND` alerts here.

---

## Files

```
darknetra/monitor/
├── models.py          Watchlist, WatchlistItem, MonitorRun, MonitorHit, Alert
├── validation.py      validate_item(type, value) → normalised value + variants (uses plan 04 validators and transliteration)
├── scheduler.py       MonitorScheduler(start/stop, add_item, remove_item, reschedule, run_now, catch_up)
├── runner.py          run_item(item_id, *, manual=False) → MonitorRun
├── adapters.py        per-item-type source plan → list[Hit]
├── dedupe.py          is_new(session, item_id, hit) ; content_hash(hit)
├── triage.py          score(hit, item, context) → TriageResult(relevance, reasons, alertable)
├── alerts.py          raise_alert(...), ack, dismiss, escalate, summarise_overflow, changes_since
├── trends_bridge.py   promote trend candidates (plan 07) into TREND alerts
darknetra/tools/impl/monitoring.py   add_watchlist_item, list_alerts, changes_since
darknetra/api/v1/routes/watchlists.py alerts.py (replace stubs)
alembic/versions/0009_monitoring.py
tests/unit/monitor/test_validation.py test_dedupe.py test_triage.py test_alert_cap.py test_scheduler.py
tests/integration/test_watchlist_api.py test_monitor_run.py test_alert_lifecycle.py test_changes_since.py test_catch_up.py
```

---

## Interfaces

### Items

```python
class ItemType(StrEnum): KEYWORD, ALIAS, WALLET, PGP_FINGERPRINT, ONION_DOMAIN, TELEGRAM_CHANNEL, IMAGE_HASH
class WatchlistItemIn(BaseModel):
    type: ItemType; value: str; variants: list[str] = []; sources: list[str] | None = None; interval_seconds: int | None = None; note: str | None = None
```

Validation and normalisation by type: KEYWORD → casefold, NFC, auto-add transliteration variants (Latin/Devanagari/Gurmukhi) when the term is in the lexicon or looks Indic; ALIAS → casefold handle without `@`; WALLET → checksum-valid BTC/ETH/TRON (plan 04) else 422; PGP_FINGERPRINT → 40 hex; ONION_DOMAIN → v3; TELEGRAM_CHANNEL → public `@name`/`t.me/name` only; IMAGE_HASH → 16 hex (pHash) or an evidence code whose image hash is used.

Default sources per type (subset of plan 08 tools; each is skipped when the case policy or offline mode disallows it):

| Type | Sources | Interval default |
|---|---|---|
| KEYWORD | `web_search(ddgs)`, `web_search(tavily)`, `onion_search`, `telegram_channel_read` (each channel item on the case) | 6 h |
| ALIAS | KEYWORD sources + `username_lookup` once per 24 h | 6 h |
| WALLET | `chain_lookup` (new txs since last cursor), `sanctions_check` | 1 h |
| PGP_FINGERPRINT | `keyserver_lookup`, `onion_search` | 24 h |
| ONION_DOMAIN | `onion_lookup`, `onion_fetch` (only when Tor enabled) | 6 h |
| TELEGRAM_CHANNEL | `telegram_channel_read(since=last_message_id)` | 30 min |
| IMAGE_HASH | compared against every new capture and upload (event-driven, not scheduled) | — |

### Scheduler

- `AsyncIOScheduler` started in the app lifespan; job id = item id; trigger `IntervalTrigger(seconds=interval, jitter=int(interval*0.1))`; `misfire_grace_time=3600`; `coalesce=True`; `max_instances=1`.
- `catch_up()` on startup: items with `next_run_at < now` are queued spaced 5 s apart.
- `settings.monitor_interval_override` (demo mode: 120 s) applies to every item while set.
- Per-source hourly caps come from the case policy through the capture gate; a `RATE_LIMITED` result schedules the next run after `retry_after` and does not count as an error.
- One failing source never blocks the others; errors are recorded per source in `monitor_runs.errors`.

### Runner

`run_item(item_id)`: load item + case (skip if case not OPEN or item inactive) → for each source: call the tool with `ToolContext(requester=WATCHLIST_ITEM, thread_id=None)` → collect `Hit`s → `dedupe.is_new` → for new hits ensure a capture exists (search-hit JSON or fetched page) → `extract` runs via the gate → `triage.score` → `alerts.raise_alert` when alertable → update `item.state` (cursors: last tx id, last message id, last search fingerprint) → persist `MonitorRun(new_hits, errors)` → `store.changed(hit|alert)`.

### Dedupe

`content_hash = sha256(normalised(url) + "\n" + normalised(snippet or body[:4000]))`; unique `(item_id, content_hash)`; URL-only fingerprint table `monitor_seen_urls(item_id, url_hash, first_seen, last_seen)` so re-ranked results with changed snippets still count as seen unless the body hash changed. For WALLET items dedupe is by transaction id; for TELEGRAM by message id.

### Triage

```python
@dataclass class TriageResult: relevance: float; alertable: bool; reasons: list[str]; diversity: dict
def score(hit: Hit, item: WatchlistItem, ctx: TriageContext) -> TriageResult
```

Rules (deterministic, always run): +0.4 exact variant match in title/snippet, +0.2 per additional distinct variant (max +0.4), +0.2 novelty (domain/sender never seen for this item), +0.1 source class weight (DARK 0.1, TELEGRAM 0.1, SURFACE 0.05, CHAIN 0.2), −0.3 when the hit is a known news/aggregator domain and the item is a KEYWORD (negative context, plan 07 cues on the snippet). Optional model pass (`settings.triage_model_enabled`, Sonnet 5 through the Anthropic SDK): given the excerpt only (≤ 1,200 chars) and the item, returns `relevance ∈ [0,1]` with one sentence; blended 50/50 with the rule score; never sees raw pages. Threshold `alertable` at 0.6.

Diversity gate: KEYWORD/ALIAS alerts require ≥ 2 distinct domains/senders/channels across hits for the item in the trailing 24 h; identifier items (WALLET, PGP_FINGERPRINT, ONION_DOMAIN, IMAGE_HASH) alert on the first new hit. Hits below threshold or gated remain visible in `/monitor/hits` with their reasons.

### Alerts

```python
class AlertKind(StrEnum): NEW_HIT, TREND, WALLET_ACTIVITY, KEY_CHANGE, ONION_STATUS, IMAGE_MATCH, MONITOR_ERROR
```

- `raise_alert(case, kind, title, summary, evidence_ids, item_id, diversity, config_version)`; per-case cap 20/hour: beyond it, hits attach to a single `OVERFLOW` summary alert for the hour (scenario 31).
- Lifecycle: `OPEN → ACKNOWLEDGED | DISMISSED | ESCALATED`; `escalate(alert, rationale)` creates a `CANDIDATE` finding with the alert's evidence, links `finding_id`, and pins it to the case's default thread if one exists; every transition is a decision row (plan 07 `decide(target_type=ALERT)`) and an audit event.
- `MONITOR_ERROR` alerts when a source fails 3 consecutive runs (one per source per day).
- `changes_since(case, since)` → `{evidence: n + codes[10], hits: n, alerts: [...], decisions: [...], candidates_rescored: n}` from indexed timestamps; used by the tool and the endpoint.

### Trends bridge

Daily job (and on demand): `trends.candidates(case)` → for each candidate term not alerted in the last 7 days create `TREND` alert with series excerpt, z-score, diversity and `config_version`.

### Image hash items

On every `store.changed(evidence)` for an image (upload or capture): compute pHash distance against active IMAGE_HASH items of the case; distance ≤ 8 → hit + `IMAGE_MATCH` alert.

### Endpoints (replace stubs)

`POST/GET /watchlists`, `POST/GET/PATCH/DELETE /watchlists/{wid}/items[/{iid}]` (deactivate rather than delete when hits exist), `POST /items/{iid}/run` (manual; respects caps; returns the run), `GET /monitor/runs?item_id`, `GET /monitor/hits?item_id&alertable`, `GET /alerts?status&kind`, `POST /alerts/{aid}/ack|dismiss|escalate {rationale}`, `GET /changes?since`.

Tools: `add_watchlist_item`, `list_alerts {status?}`, `changes_since {since}` for CASE_LEAD.

---

## Tasks

- [ ] **T1 migration 0009 + models + validation** (scenario-style tests for each item type).
- [ ] **T2 scheduler** with a fake clock and a stub runner: add/remove/reschedule, override, catch-up spacing, max_instances (scenario 32).
- [ ] **T3 runner + adapters** using plan 08 tools with mocked adapters; per-source error isolation; cursors.
- [ ] **T4 dedupe** (scenario 29) and **triage** (scenario 30) unit tables.
- [ ] **T5 alerts service** with cap and overflow (scenario 31), lifecycle, escalate → finding.
- [ ] **T6 trends bridge + image-hash hook**.
- [ ] **T7 endpoints + tools + changes_since**.
- [ ] **T8 integration**: demo-mode interval 120 s, add WALLET W1 and KEYWORD "safed line"; with mocked sources returning a new tx and three diverse hits, an alert appears within one scheduler tick; `changes_since` lists it.

## Acceptance gate

Scenarios 29–32 pass; the integration above passes; `GET /alerts` shows OPEN alerts with evidence codes that resolve; dismiss and escalate are audited and escalate creates a finding.

## Handoff

Plan 10 renders alerts, hits and monitor summaries into the pack and the walkthrough adds the watchlist step.
