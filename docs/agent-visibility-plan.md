# M3/M5 agent execution visibility

User-authorized architectural extension, 2026-09-06. No frontend implementation.

The lead model chooses registered tools or bounded specialist delegation. Policy,
case isolation, evidence capture and claim verification remain backend-owned. Use
the existing Claude SDK/Ollama and MCP registry; do not replace the backend merely
to adopt a frontend library. Independent frontend research will be recorded in the
root frontend.md.

## Deliverables

1. Typed, durable activity node updates in the existing append-only run event log.
   Stable IDs relate lead agent, delegation, specialist, tool and capture phases.
   Status and public operational summaries never contain private chain-of-thought.
2. Case/thread/run-scoped execution snapshot with nodes, edges and an event cursor.
   Reconnect fetches a snapshot then replays SSE after that cursor. Existing SSE
   events stay compatible; completed runs and interrupted activities remain visible.
3. Tool/integration metadata and actual transport labels. Robin is currently a local
   adapter exposed through DARKNETRA's MCP bridge, not its own remote MCP server.
   Show actual fetching/persistence/parsing stages; do not invent provider progress.
4. One-level, bounded specialist delegation through a registered tool, inherited
   authorization, isolated worker context, shared budget and cancellation, verified
   worker results. Persist worker activity under the parent run. Independent resumable
   child runs and parallel worker scheduling are outside this bounded increment.
5. Tests for event replay, repeat tool calls, denials/cancellation, case isolation,
   delegation limits and budgets. Update OpenAPI, Docker, and frontend integration docs.

Existing case work, private-chat roadmap and monitoring remain intact. No model key
is configured in the demo; provider-controlled delegation can be tested with bounded
test harnesses without claiming a live model test.
