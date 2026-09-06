# ADR-0001: Backend first, frontend against a frozen contract

Date: 2026-09-06 · Status: accepted

## Decision
Build the FastAPI backend as a standalone service with an OpenAPI contract frozen at milestone M0. The Next.js frontend is a separate project built against `docs/openapi.json` with generated TypeScript types and MSW mocks, integrated from Tuesday H+4 onward.

## Why
- Five people, two prep days and 24 hours: the API is the integration point that lets four lanes work in parallel.
- The demo can be proven end to end over HTTP (`scripts/demo_walkthrough.py`) before any screen exists, which de-risks the UI.
- The same contract serves Hermes, Codex and any second front-end (LibreChat/Open WebUI) later.

## Consequences
- Breaking API changes after M0 require a version bump and a note to the frontend owner.
- SSE event schema (§7.1) is part of the contract.
- No Docker on the dev laptop: native Postgres 16 + pgvector; Docker Compose is for other machines.
