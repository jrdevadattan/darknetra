# AI Elements workspace rebuild (M1–M7 frontend)

The user replaces the Chakra design with AI Elements. The entire frontend presentation,
state management and chat integration are rebuilt; backend case boundaries remain authoritative.

1. Install selected official AI Elements (message, conversation, prompt-input, reasoning,
   tool, agent, terminal, canvas, sources) and shadcn primitives. Dark graphite theme,
   Geist typography, responsive navigation, and light/system choices.
2. Generate API types from the frozen OpenAPI document. Build cookie/CSRF client,
   single-flight refresh, scoped caches and abortable streams with snapshot reconciliation.
3. Provide real private and case conversations, provider/budget choices, evidence
   references, user-requested new cases, and run cancellation. Activity graph, timeline
   and console use the same recorded events; only public operational summaries appear.
4. Case screens use authorized REST records for evidence, retrieval, findings, relationships,
   watchlists/attempts, alerts, reports, members and policy. Plugins expose actual availability.
5. Test auth, CRLF and chunked SSE, reconnect, scope switching, forms and responsive
   browser behavior with synthetic case data. Build and smoke-test Docker.
6. Update frontend.md and README, review the change, and push dev as already requested.

Terminal is a read-only operational event log. Arbitrary shell execution, arbitrary
repository/plugin installation and private model reasoning are not part of the backend.
Runtime choices show the stored backend harness, including deterministic override.
