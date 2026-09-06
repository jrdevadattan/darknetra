# Plan 17 — Scenario matrix: every case and the test that proves it

Each row is a test in `tests/scenarios/test_s<NN>_<slug>.py` (or the unit/integration file named) and is referenced by the plan that implements it. A milestone gate lists the rows it must pass. Rows 1–44 are the original set; 45–60 were added while writing the detailed plans.

| # | Scenario | Expected behaviour | Implemented in | Test |
|---|---|---|---|---|
| 1 | Same file uploaded twice | second call returns the existing evidence with `duplicate:true`; custody VERIFIED | 02 | `test_s01_duplicate_upload.py` |
| 2 | Corrupted or encrypted PDF | stored; derivative FAILED or PARTIAL with reason; listed | 02 | `unit/ingest/test_pdf.py` |
| 3 | Image-only PDF | `TEXT_NOT_AVAILABLE`; `transcribe_image` per page works; OCR job in 16 | 02, 06 | `test_s03_image_only_pdf.py` |
| 4 | ZIP bomb, traversal, symlink, nested archive | QUARANTINED with warning; no extraction | 02 | `unit/ingest/test_zipsafe.py` (Hypothesis) |
| 5 | Upload above the cap | 413 `VALIDATION` before buffering | 02 | `test_s05_upload_cap.py` |
| 6 | Unknown MIME or extension mismatch | signature decides; warning recorded | 02 | `unit/ingest/test_sniff.py` |
| 7 | WhatsApp export with 12-hour times and multi-line messages | MESSAGES correct; timezone recorded | 02 | `unit/ingest/test_whatsapp.py` |
| 8 | Telegram JSON with edits, replies, media | links kept; media as child evidence | 02 | `unit/ingest/test_telegram.py` |
| 9 | Hinglish query for a Devanagari passage | lexical via transliteration and dense hit; span resolves to raw | 05 | `test_s09_multilingual_search.py` |
| 10 | Search from case A must not see case B | zero hits | 05 | `contract/test_isolation.py` |
| 11 | Wallet with failing checksum | `valid:false`, confidence 0.3, not canonicalised | 04 | `unit/extract/test_crypto.py` |
| 12 | Fingerprint text contradicts the key | computed fingerprint wins; mismatch warning | 04 | `unit/extract/test_pgp.py` |
| 13 | Substance mentioned in a news article | activity LOW_SIGNAL | 07 | `unit/analytics/test_activity.py` |
| 14 | Two aliases share only the escrow wallet | wallet contribution 0 with reason; WEAK | 07 | `test_s14_escrow_decoy.py` |
| 15 | Stylometry alone scores high | cannot reach STRONG | 07 | `unit/analytics/test_link_scoring.py` |
| 16 | New evidence after a decision | version 2 candidate; decision stays on v1; `rescored` flag | 07 | `test_s16_rescore.py` |
| 17 | Two analysts decide the same candidate | second gets 409 with the existing decision | 07 | `test_s17_decision_conflict.py` |
| 18 | Model cites a nonexistent evidence code | revision request; then `verified:false`; run completes | 06 | `test_s18_bad_citation.py` |
| 19 | Model passes a foreign case id | ToolContext ignores model-supplied case ids | 06 | `unit/tools/test_invoke.py` |
| 20 | Tool timeout or MCP server down | step error; model told; run continues; health updated | 06, 08 | `test_s20_tool_failure.py` |
| 21 | Provider rate limit or network blip | two retries with backoff; then `run.error` with explanation | 06 | `unit/agent/test_harness_retries.py` |
| 22 | Thread budget exhausted | run ends BUDGET; budget editable | 06 | `test_s22_budget.py` |
| 23 | Cancel mid-run | task cancelled; partial message persisted; in-flight tools recorded | 06 | `test_s23_cancel.py` |
| 24 | Offline mode | offline harness; network tools `NETWORK_REQUIRED`; evidence lane works | 06, 08, 10 | `test_s24_offline.py` |
| 25 | Tor blocked at the venue | `onion_fetch` UNAVAILABLE; clearnet `onion_search` works; replay snapshots | 08 | `test_s25_tor_unavailable.py` |
| 26 | Dark capture with images | images QUARANTINED; release audited | 08 | `unit/capture/test_gate.py` |
| 27 | Prompt injection inside a capture | excerpt only; no tool call follows injected text | 08 | `test_s27_injection.py` (FakeHarness asserts no unexpected tool call) |
| 28 | Person lookup on a typed name | `POLICY_DENIED`; logged | 08 | `unit/policy/test_rules.py` |
| 29 | Watchlist source repeats hits | dedupe; `new_hits=0`; no alert | 09 | `unit/monitor/test_dedupe.py` |
| 30 | One spammy alias repeats a term | diversity gate blocks the alert | 09 | `unit/monitor/test_triage.py` |
| 31 | Alert storm | cap 20 an hour; overflow summary alert | 09 | `unit/monitor/test_alert_cap.py` |
| 32 | Scheduler down for hours | catch-up with spacing; caps respected | 09 | `test_s32_catch_up.py` |
| 33 | Demo mode | 120-second interval; replay cache; SYNTHETIC banner flag | 10 | `test_s33_demo_mode.py` |
| 34 | Legal hold | purge jobs skip; export allowed | 01, 14 | `test_s34_legal_hold.py` |
| 35 | Viewer tries to decide or view originals | 403 with stable code; audited | 01 | `contract/test_rbac_matrix.py` |
| 36 | Report with unverified claims | sentences dropped and listed; report generated | 10 | `unit/reports/test_narrative_claims.py` |
| 37 | Sanctions key missing | OFAC list fallback, source labelled | 07, 08 | `unit/analytics/test_sanctions.py` |
| 38 | GNN unavailable | `gnn:null` with reason; rest proceeds | 07 | `unit/analytics/test_gnn.py` |
| 39 | Address not in ledger, or Monero | explicit reasons; no guess | 07 | `test_s39_wallet_reasons.py` |
| 40 | Re-ingest with a new extractor version | new versions; old kept | 02, 04 | `test_s40_reprocess.py` |
| 41 | Audit tampering attempt | trigger rejects UPDATE and DELETE | 00 | `integration/test_migrations.py` |
| 42 | SSE reconnect after a drop | `Last-Event-ID` replays from the log | 06 | `test_s42_sse_reconnect.py` |
| 43 | Case closed | threads read-only; monitoring paused; reports generatable | 01, 06, 09 | `test_s43_closed_case.py` |
| 44 | Service token with `alerts:read` only | can list alerts; cannot run threads | 01 | `contract/test_tokens.py` |
| 45 | Two threads run concurrently in one case | both stream independently; per-case cap 3 → `UNAVAILABLE` on the fourth | 06 | `test_s45_concurrent_threads.py` |
| 46 | Unicode and very long filenames | stored safely; original name preserved in metadata; storage key is the hash | 02 | `unit/ingest/test_filenames.py` |
| 47 | Evidence code allocation under concurrency | codes unique and gap-free per case | 02 | `test_s47_code_allocation.py` |
| 48 | Refresh token reuse | all sessions revoked; audit event | 01 | `integration/test_refresh_rotation.py` |
| 49 | Service token expiry | 401 after `expires_at`; `last_used_at` updated at most once a minute | 01 | `contract/test_tokens.py` |
| 50 | Watchlist item deactivated while hits exist | item inactive; hits and alerts remain readable | 09 | `test_s50_item_deactivate.py` |
| 51 | Source fails three runs in a row | one `MONITOR_ERROR` alert per source per day | 09 | `unit/monitor/test_monitor_error.py` |
| 52 | Harness readiness fallback | Claude CLI or key missing → offline harness selected; `/health/ready` degraded | 06, 10 | `test_s52_harness_fallback.py` |
| 53 | Embedding model missing | lexical-only search; `dense_available=false`; readiness degraded | 05 | `integration/test_index_and_search.py` |
| 54 | Report regeneration | version+1 with its own hash; previous version still downloadable | 10 | `integration/test_report_generate.py` |
| 55 | Escalated alert | CANDIDATE finding created and linked; decision row recorded | 09 | `integration/test_alert_lifecycle.py` |
| 56 | Ledger import with malformed CSV | 422 with row numbers; nothing imported (transactional) | 07 | `test_s56_ledger_import.py` |
| 57 | Quarantined dark image released | READY; custody RELEASED; audit with rationale; served inline afterwards | 02, 08 | `integration/test_quarantine_flow.py` |
| 58 | Trend candidate with only one source | no TREND alert; series still visible | 07, 09 | `unit/analytics/test_trends.py` |
| 59 | Summary refresh | thread summary regenerated every 6 assistant messages from persisted messages only | 06 | `integration/test_threads_api.py` |
| 60 | Backup and restore | every evidence hash verifies after restore; walkthrough passes with the FakeHarness | 10 | `integration/test_backup_restore.py` |
