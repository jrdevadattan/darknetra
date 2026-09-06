# Backend completion audit — 6 September 2026

This increment follows the existing M0–M6 plan and the requested case workspace,
private chats, plugin controls and model-provider support. The frontend remains a
separate implementation track. Tests and configured dependencies determine completion;
an unavailable provider is not a completed live acceptance test.

## Work items

1. Audit the plans against source and tests; record missing operations and dependencies.
2. M2: implement local embedding loading, validated vectors, semantic and RRF hybrid
   search, model/version isolation, incremental reindexing and honest lexical fallback.
3. M3: add NVIDIA NIM through the shared harness/tool/policy/event contracts.
4. Workspace: implement private normal chats without weakening case-table isolation,
   and expose supported plugin configuration through authenticated backend contracts.
5. Close concrete correctness gaps found by the audit; retain explicit unavailable
   states for absent trained assets and unsupported external integrations.
6. Add one migration for this increment, regenerate OpenAPI, run the fresh-database
   suite and Docker checks, and update the frontend and implementation records.

## Working decisions

- Work is on `codex/complete-backend-gaps`; the existing checkout retains its configured
  local Python environment and Docker volume. The user's earlier explicit instruction
  authorises publishing verified backend changes to main and dev. Production code is
  preserved; its pipeline-only cleanup is a separate completed commit.
- Preserve the evidence/case invariants. Private chat data uses separate owner-scoped
  storage; it cannot silently gain case evidence or investigation tools.
- Registered and reviewed integrations are the plugin boundary. Arbitrary executable
  installation or untrusted MCP servers require a separate sandbox/gateway implementation.
- Local model inference uses explicitly provisioned assets, never an implicit download
  during an evidence upload or search. Model quality and live provider availability are
  measured separately from adapter tests.

## Continuation after the core verification

The initial completion suite passed 373 tests with 87 API paths and migration 0003.
The repeated completion request extends item 5 with bounded M1 Office/PDF extraction,
M6 persisted monitoring attempts/restart recovery, and current-version digest counts.
These additions need no database migration. They retain the one-process deployment
model and do not imply support for unprovisioned model assets or M7–M9 integrations.
