# DARKNETRA implementation plans — index

Backend-first. Each plan is independently executable by a coding agent (Codex, Claude Code) or a human, in the order below. Every plan lists the files it creates, the interfaces it exposes, task steps with checkboxes, the tests that prove it, and an acceptance gate. A plan is done only when its acceptance gate passes on a fresh database.

Overview and rationale: `docs/implementation-plan.md`. Conventions and invariants: `AGENTS.md`. Design context: the v1/v2/v3 pages linked from the overview.

## Execution order

| # | Plan | Milestone | Owner | Depends on |
|---|---|---|---|---|
| 00 | [Foundation: scaffold, config, DB, migrations, CI, contract export](00-foundation.md) | M0 | A | — |
| 11 | [API contract (schemas, errors, pagination, SSE)](11-api-contract.md) | M0 (reference) | A | 00 |
| 12 | [Data model (all tables, indexes, constraints)](12-data-model.md) | M0 (reference) | A | 00 |
| 01 | [Auth, RBAC, service tokens, cases, audit](01-auth-cases-audit.md) | M1 | A | 00 |
| 02 | [Evidence vault, upload, ingest parsers, derivatives, custody](02-evidence-vault-ingest.md) | M1 | B | 01 |
| 03 | [Synthetic case SYN-CHD-001: generator, ground truth, seed](03-synthetic-case.md) | M1 | E | 02 |
| 04 | [Extraction: normalisation, validators, lexicon, NER, canonicalisation](04-extraction.md) | M2 | B | 02 |
| 05 | [Retrieval: chunking, embeddings, hybrid search, context, eval](05-retrieval.md) | M2 | B | 02, 04 |
| 06 | [Tool registry, agent harnesses, threads, SSE, claim checker, replay](06-tools-and-harness.md) | M3 | A | 04, 05 |
| 07 | [Analytics: correlation, activity, graph, decisions, findings, wallets, trends](07-analytics-decisions.md) | M4 | C | 04, 06 |
| 08 | [Capture gate, policy engine, OSINT adapters, subagent roster](08-capture-policy-osint.md) | M5 | A, C | 06, 07 |
| 09 | [Watchlists, monitoring scheduler, triage, alerts](09-monitoring-alerts.md) | M6 | C | 08 |
| 10 | [Investigation pack, demo and offline modes, walkthrough, backup](10-reports-modes-demo.md) | M6 | E, A | 07, 09 |
| 13 | [Testing strategy and evals](13-testing-evals.md) | cross-cutting | all | — |
| 14 | [Ops: environment, compose, health, logging, backups](14-ops.md) | cross-cutting | A | 00 |
| 15 | [Frontend track (separate project, contract consumer)](15-frontend-track.md) | parallel from M0 | D | 11 |
| 16 | [Post-hackathon: reach, Hermes, Codex, Graphiti, guardrails, Tor, sharing](16-post-hackathon.md) | M7–M9 | all | 10 |
| 17 | [Scenario matrix: every case and the test that proves it](17-scenario-matrix.md) | cross-cutting | all | — |

## Global rules (apply to every plan)

- Python 3.12 via `uv`; Ruff clean; mypy strict on `tools/`, `capture/`, `policy/`.
- One Alembic migration per plan, named `NNNN_<plan>.py`; never edit an applied migration.
- Tests first where the behaviour is independently testable; record the failing (RED) run in the PR, then the passing run.
- No PR without fresh verification output (`make test` log excerpt) in its description.
- Never fabricate results: a tool that cannot do its job returns a typed error (`NETWORK_REQUIRED`, `POLICY_DENIED`, `UNAVAILABLE`), never an empty success.
- Case isolation in every query; the isolation contract test from plan 05 must stay green.
- Synthetic fixtures only; label them `SYNTHETIC`.
- Every long job goes through `jobs.runner` so it can move to a worker later.

## Milestone gates

- **M0** `make dev` boots; `/health/ready` green; `docs/openapi.json` exported with every path from plan 11.
- **M1** seed script ingests SYN-CHD-001 through the API; evidence list shows ≥ 9 items with derivatives; scenarios 1–8.
- **M2** retrieval eval passes; planted indicators observed with correct spans; scenarios 9–12.
- **M3** cited answer streams over SSE; scenarios 18–24; fake-harness integration test green.
- **M4** planted alias pair STRONG, decoy WEAK; accept turns edge CONFIRMED; wallet assessment returns GNN + sanctions; scenarios 13–17, 37–39.
- **M5** captures with hashes from a thread question; denials logged; scenarios 25–28; offline degrade.
- **M6** alert within 2 minutes in demo mode; report with appendix; scenarios 29–36, 40–44; `demo_walkthrough.py` completes with no UI.
