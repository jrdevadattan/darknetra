# AGENTS.md — how to work in this repository

DARKNETRA: an evidence-first narcotics-intelligence case workspace for authorised investigators.
Backend first (FastAPI, Python 3.12, PostgreSQL + pgvector). Frontend (Next.js) is a separate track that consumes the frozen API contract.

Read `docs/implementation-plan.md` before changing anything. Section numbers below refer to it.

## Invariants (a PR that breaks one is rejected)
1. Evidence is immutable and content-addressed (§1, §6). Never modify or hard-delete evidence, audit events or decisions.
2. Capture before reasoning (§10). Every external fetch goes through `capture.gate`; tools return evidence codes and excerpts, never raw pages.
3. Models never write facts (§1). Only deterministic code writes observations, candidates, edges, alerts; only a human decision confirms a finding.
4. Every claim cites (§9). Final answers carry `claims[]` with evidence codes; the claim checker runs on every assistant message.
5. Case isolation (§13). Every case-scoped query filters by `case_id`; there is a contract test for cross-case leakage.
6. Read-only outside world (§10). GET/HEAD only; no logins, forms, purchases, messages, CAPTCHA solving; Tor only from the collector behind the case switch.
7. Everything audited (§18). Mutations, tool calls, captures, denials, exports.
8. Offline degrades, never breaks (§9.2).
9. Synthetic data is labelled SYNTHETIC; no real vendors, keys, locators or personal data in fixtures (§20).

## Conventions
- Python 3.12 via `uv` (do not use the system Python 3.14). Ruff for lint/format, mypy strict on `tools/`, `capture/`, `policy/`.
- Async SQLAlchemy 2 + Alembic. One migration per PR; never edit an applied migration.
- Pydantic v2 models for every API and tool contract. Tool specs live in `backend/darknetra/tools/registry.py`; add a tool by adding a spec + impl + tests, never by editing the harness.
- Errors use the stable codes in §7. Unknown and inaccessible cases both return 404.
- Tests accompany code: unit for validators/parsers/scoring, integration for services, scenario tests reference the row number in §19.
- No secrets in code or logs. Configuration through `pydantic-settings`; document every variable in `.env.example`.
- Commit messages: `feat|fix|test|docs|chore(scope): summary`. Do not commit generated data except `docs/openapi.json`.

## Commands
- `make dev` — sync, migrate, seed SYN-CHD-001, run API on :8000
- `make test` — ruff + mypy + pytest
- `make openapi` — regenerate `docs/openapi.json` (CI fails on breaking changes without a version bump)
- `make demo` — seed + `scripts/demo_walkthrough.py` (end-to-end over HTTP, no UI)

## When unsure
- Prefer the deterministic path over a model call.
- Prefer returning `NETWORK_REQUIRED` / `POLICY_DENIED` over silently skipping.
- Ask in the PR description; do not widen scope. The plan's milestone (M0–M9) each task belongs to must be named in the PR title.
