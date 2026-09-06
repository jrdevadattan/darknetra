# M5/M6 reusable tools and agent workspace direction

Implementation addendum, 2026-09-06. This does not replace the evidence, isolation,
read-only source, or human-decision invariants in implementation-plan.md.

The requested product is an agent workspace: cases correspond to projects, each
case can contain chats and be shared with authorised members. Independent personal
chats must be separate from cases. A lead agent should coordinate bounded specialist
runs; monitoring corresponds to scheduled work. Plugins provide typed capabilities.

## Current implementation boundary

Case membership, case threads, persisted runs/events, tool policy, capture, lexical
RAG with citations, watchlists and scheduling exist. The agent visibility increment
now adds bounded one-level specialist execution through `delegate_task`, with durable
activity records and a case-scoped execution snapshot. See `agent-visibility-plan.md`
and root `frontend.md`. Semantic embeddings, independent personal chats and installable
plugin management remain unimplemented. Native Agent/Task and arbitrary SDK plugins
stay disabled; delegation goes through the case-authorized registry instead.

Normal chats need their own owner-scoped data model and must not gain case tools or
implicitly search cases. Sharing a case means authenticated membership, not a public
evidence link. All child agents must inherit the case, actor, source restrictions and
shared budget, with persisted parent/child run IDs, cancellation and citation checks.
Monitoring needs bounded collectors, deduplication, histories and explicit unavailable
results. Dark-site monitoring additionally requires the isolated Tor collector and
the case switch; a clearnet index result does not establish current site availability.

## Integration tasks

1. Pin and inspect Robin and Agent Reach, preserve licenses, select reusable parts.
2. Add Robin's deterministic index parser behind the capture gate; no upstream direct
   network/model pipeline. Its result is a cited index observation.
3. Add typed surface SERP and RSS tools. Use GET search, parse only captured bytes,
   bound outputs and reject unsafe locators. Support a configured public SearXNG JSON
   endpoint. Do not weaken the public transport to accept private endpoints.
4. Use Agent Reach locally for installation/diagnostics; adapt its public-web channel
   checks into an evidence-capturing Jina Reader tool. Jina output is an intermediary
   representation and must be labelled as such. Reuse Trafilatura on captured HTML.
5. Expose the same registry through a real MCP stdio server bound to one case and a
   revocable service token. Validate authorisation on each call; no arbitrary commands.
6. Verify parsers, capture ordering, case isolation, token revocation and MCP protocol;
   rebuild Docker and run benign live diagnostics. Distinguish tested, unavailable,
   and configured-but-unprobed providers in the completion record.

## Next platform milestones

- M2: dense embedding job, model identity/version, hybrid ranking and retrieval evals.
- M3 follow-up: independently resumable/parallel child runs beyond the implemented
  sequential, bounded worker activity within a root run.
- M1/M3 extension: private standalone chats, explicit attach/import into a case.
- M5 extension: reviewed plugin manifests, version pins, case allowlists and health.
- M6/M9: durable monitoring execution and isolated read-only Tor collection.

These are separate acceptance milestones; this integration increment does not claim
the full Codex-style platform is complete. Frontend navigation remains a separate track.
