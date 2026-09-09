# Plan 20 — UI completion: missing panels and demo polish

Post-build · Owner D · Frontend in `frontend/` (Next.js 16, React 19, AI Elements, React Flow, TanStack Query). Depends on plan 19 only where noted. All data comes from the API; no panel may render model prose as facts.

Verified baseline (8 Sep): login and forced password change; private workspace with provider picker; case workspace with Overview, Evidence, Search & retrieval, Entities, Relationships, Findings & decisions, Monitoring, Alerts, Reports, Sharing & policy, Audit trail; Tools & integrations; Settings with tokens; case conversation with citations, sources, and the Agent activity panel (graph, timeline, output). 17 unit tests and 3 Playwright scenarios pass.

---

## U1 — Trends panel (P0, backend ready)
- Route: sidebar item `Trends` between Alerts and Reports; data `GET /cases/{id}/trends?window_days=30` (`series[]`, `new_term_candidates[]`).
- Component: `components/workspace/case-analysis-views.tsx` → `TrendsView`: a window selector (7/30/90 days), a Recharts line chart per selected term (count per day with the z-score as a tooltip), a table of series with `candidate` badge and reasons, and a "New term candidates" list (term, frequency, diversity, score) with a button that opens the taxonomy admin (U6) for admins.
- Acceptance: the planted term shows a spike with the candidate badge; the control term does not.

## U2 — Wallets panel (P0, backend ready)
- Route: `Wallets` after Entities; data `GET /cases/{id}/wallets`, `POST /cases/{id}/wallets/assess {address, chain, live}`.
- Component: `WalletsView`: assessment form (address, chain, live toggle disabled with a tooltip when `offline_mode`), table of assessments (address, chain, GNN class and probability or `gnn_unavailable_reason`, sanctions or reason, live summary evidence chip, assessed at, version), detail drawer with the threshold and caveat text verbatim from the API.
- Acceptance: assessing W1 shows either the GNN result (after plan 19 P1-2) or the explicit "address not in ledger" reason; never a blank.

## U3 — Case list hygiene (P0)
- Sidebar and `/cases`: hide `ARCHIVED` by default with a toggle; sort OPEN demo case first; show the case code; a per-case kebab with Close/Reopen/Archive for LEAD/OWNER (endpoints exist).
- Acceptance: after archiving the test cases, the sidebar shows `CHD-2026-0002` alone.

## U4 — Members picker (P0)
- Sharing & policy → "Add member": replace the UUID field with a searchable list from `GET /users` (admin) or, for non-admins, a username field validated by a `GET /users?q=` lookup once plan 19 adds it; show role select and the last-owner rule error verbatim.
- Acceptance: adding `analyst.demo` by name works for an OWNER.

## U5 — Origin and environment guard (P0)
- On the login screen, if `window.location.hostname` is `127.0.0.1`, show a one-line notice "Open this workspace at http://localhost:3000 (the server permits only that origin)". Read the permitted origin from a tiny `GET /api/v1/health/live` extension or hard-code the notice for the demo.
- Acceptance: the trap seen today cannot recur silently.

## U6 — Administration screens (P1)
- Users: list, create (username, display name, global role, initial password), deactivate (`GET/POST /users`, `PATCH /users/{id}`).
- Taxonomy: list, add variant, toggle active (`/admin/taxonomy`), with language and script columns; link from U1 new-term candidates.
- Plugins: the existing enable/disable per integration plus the case allowlist editor already in Sharing & policy; add manifest hash display and health probe button per tool (`POST /tools/{name}/health`).
- Acceptance: an admin can onboard a second investigator without the API docs.

## U7 — Overview upgrades (P1)
- Digest card from `GET /cases/{id}/digest?since=` (pending candidates, top alerts, recent findings) with a "since" selector; timeline filters by kind; readiness chips (harness, embedding, collector) copied from `/health/ready` so the presenter sees the mode at a glance.

## U8 — Evidence detail (P1)
- Derivative viewers: MESSAGES rendered as a chat transcript with sender, time and message index (line numbers match citations); ROWS as a table; IMAGE_META with a thumbnail for READY images (original download stays permissioned); OCR blocks with regions once plan 19 P1-1 lands.
- Context drawer: when a citation chip is clicked, highlight the exact span using `/context` and show the line number; add "Copy citation".
- Quarantine: show the reason and a Release button for the permitted role.

## U9 — Findings and candidates (P1)
- Candidate detail: feature table (name, family, value, weight, contribution, evidence chips, explanation) and contradictions; band legend; "re-scored" flag with a link to the superseded version.
- Decision dialog: show the existing decision on 409 with a supersede option for LEAD/OWNER.
- Findings: kind badge (observed / model / candidate / confirmed), promote flow, pin to conversation.

## U10 — Monitoring and alerts (P1)
- Item rows: next run, last run, per-source backoff, suspension reason; run history drawer with errors; "Pause all" for a case.
- Alerts: group by kind; overflow alert explanation; escalate creates a finding and navigates to it.

## U11 — Reports (P1)
- Show `claim_check.dropped` and `redaction` summaries; disable download of unredacted packs for roles without EXPORT; show a generation error reason when the backend adds it (plan 19 note); PDF via print stylesheet button.

## U12 — Conversation and activity polish (P1)
- Suggested prompts on the case landing (already present) should map to the six demo questions; show the harness name and cost in the composer footer; cancel button visible during runs; replayed runs marked.
- Activity graph: auto-fit on new nodes; node inspector shows evidence chips that open the context drawer; timeline filters by status; output log copy button.

## U13 — Accessibility, mobile, performance (P2)
- Keyboard alternative table for both graphs; focus order in dialogs; reduced-motion respect; virtualised evidence and entity tables above 500 rows; cursor pagination everywhere the API supports it.

## U14 — Test coverage (P1)
- Playwright: add scenarios for candidate decision and promote, monitoring run-now and alert escalate, report generate and download, Trends and Wallets panels, archive case, origin notice. Keep the existing three.
- Vitest: reducers for the activity graph merge (duplicate sequences, interrupted nodes) and the trends chart data mapping.

---

## Demo script for the UI (5 minutes, Wed 9 Sep)

1. Login at `http://localhost:3000` → `CHD-2026-0002` (banner `SYNTHETIC DEMO`, mode chip shows the harness).
2. Evidence: upload one more synthetic screenshot; watch status move to READY; open the detail; verify hash.
3. Conversation: "Which seller handles could be the same operator? Explain." → citations checked, sources chips, activity graph animating; open the STRONG candidate from a chip; decide ACCEPT with a rationale; Relationships shows the solid edge.
4. Wallets (U2): assess W1; show the GNN result or the honest reason.
5. Monitoring: add the wallet and the planted phrase; within two minutes an alert appears; escalate to a finding.
6. Trends (U1): the spike with diversity; new-term candidate.
7. Reports: generate a pack; show the appendix and the SHA-256.
8. Close on Tools & integrations: point at the read-only capture gate, the disabled dark lane, and the policy switches.
