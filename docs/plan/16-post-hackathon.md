# Plan 16 — Post-hackathon: reach, Hermes, Codex, richer ingest, knowledge, guardrails, collector, sharing

Milestones M7 (weeks 1–2), M8 (weeks 3–4), M9 (weeks 5–8). Each item is a mini-plan with files, interface and acceptance. The invariants of plan 00 apply unchanged; in particular every new source passes the capture gate and every new agent surface uses the DARKNETRA API, never the database.

---

## M7 — Reach and richer ingest

### 7.1 Hermes Agent as the investigator's pocket agent
- Files: `integrations/hermes/darknetra_tool.py` (Hermes custom tool), `integrations/hermes/skills/` (symlink to `skills/`), `integrations/hermes/README.md`.
- Backend: service tokens with scopes `cases:read alerts:read alerts:handle threads:run monitor:run`; endpoint `GET /cases/{id}/digest?since=` returning a compact summary for messaging (counts, top alerts, pending candidates, last findings).
- Hermes tool functions: `list_cases`, `digest(case, since)`, `ask(case, thread, question)` (posts a message, waits on SSE, returns the final message with claims as plain text with `[E-0007]` chips), `alerts(case, status)`, `ack/dismiss/escalate`, `add_watch(case, type, value)`.
- Hermes config: gateways Telegram + WhatsApp; exec tools disabled; only the DARKNETRA tool and read-only research skills; pairing approval for unknown senders; one Hermes instance per sensitive case if required.
- Cron: "every 6 hours run watchlists for case X and message me if anything is new" → calls `monitor:run` on each item then `digest`.
- Acceptance: an officer on Telegram receives a morning digest and asks a follow-up that returns a cited answer within 60 s; every call appears in the case audit with `actor_kind=TOKEN`.

### 7.2 Reach layer (agent-reach, OpenCLI, Apify, Bright Data)
- A dedicated scout host (VM or laptop) with agent-reach installed and burner browser profiles; `integrations/reach/mcp_server.py` exposes `reach_search(platform, query)` and `reach_read(platform, url_or_id)` as an MCP server whose handlers shell out to the agent-reach CLI and return structured JSON.
- Backend: register the server through the MCP gateway with `policy_tags={"surface","social"}`; all results pass `capture.gate` (`source_class=OSINT_SURFACE`, `meta.platform`).
- Apify: `apify_adapter` generalised to actors for Instagram, Facebook and YouTube; per-case monthly spend cap in the case policy; `telegram_channel_read` default switches to the Apify actor.
- Bright Data Web MCP as a fallback fetcher for pages `SafeHttp` cannot read (anti-bot), behind the same gate and a monthly cap.
- Acceptance: "where else does this handle appear?" returns captures from at least three platforms in a staging case with burner profiles; account bans are handled by `agent-reach doctor` routing without code changes.

### 7.3 Codex sandboxed analyst
- Files: `integrations/codex/analyst.py`, endpoint `POST /cases/{id}/analysis/codex {question, dataset: ledger|entities|graph|all}`.
- Flow: export the requested tables to a per-case read-only directory (`exports/<case>/<ts>/*.csv`); `Codex().thread_start(model=..., sandbox=Sandbox.read_only)`; prompt with the question and a JSON schema for the result (`{findings:[{title, evidence_refs, method, values}], notebook: str}`); run; store the result as `analytic_runs(kind=CODEX)` with the transcript; findings become DRAFT findings referencing evidence codes only (never file paths).
- `resumeThread` keeps one analyst thread per case; results never touch the vault.
- Acceptance: "cluster counterparties of W1 by first-seen week" returns a JSON result and a DRAFT finding with evidence codes.

### 7.4 Richer ingest
- Docling for PDFs and office documents (adds OFFICE to the parser matrix; layout-aware TEXT with page map); Surya OCR (`hin`, `pan`, `eng`) for scanned PDFs and screenshots with line regions → `OCR` derivative; IndicConformer 600M for audio (`ogg/opus/m4a/wav`) → `TRANSCRIPT` with timestamps and language tags; faster-whisper fallback; pyannote diarisation optional.
- All run in the jobs runner with model manifests under `models/manifests/`; missing models degrade to `Pending` with a reason.
- Acceptance: a WhatsApp voice note in Hindi becomes searchable text with timestamps; a scanned memo is OCR'd with regions and the spans resolve in the UI.

### 7.5 Playbooks as SKILL.md
- `skills/<name>/SKILL.md` with frontmatter (`name`, `description`, `tools`, `inputs`), procedure steps, decision rules, and an "evidence hygiene" section; six playbooks from the v3 page; Hermes and Claude Code load the same folder; `mcp-scan` runs over `skills/` in CI (M8).

### 7.6 TronGrid lane complete
- `chain_lookup(chain=tron)` returns TRC20 transfers with counterparties and USDT amounts; `assess_wallet` supports Tron tags; watchlist WALLET items on Tron use the transfer cursor.

---

## M8 — Knowledge and guardrails

### 8.1 Graphiti temporal graph
- Service `knowledge/graphiti.py` writing accepted findings and confirmed edges as episodes (`fact, valid_from, valid_to, evidence_codes`); query tool `temporal_facts {subject, at}` for the Case Lead; storage Neo4j or FalkorDB in a compose profile; rebuildable from Postgres (never authoritative).
- Acceptance: "what did we know about W1 on 9 July?" answers from the temporal graph with citations.

### 8.2 Image similarity
- CLIP/SigLIP embeddings for images (`image_embeddings` table, pgvector); tool `similar_images {evidence_code, k}`; the `image_family` feature in plan 07 gains an embedding-based signal with its own threshold; face matching remains out unless a written authority switch is added to the case policy and audited.

### 8.3 Tool supply-chain security
- Docker MCP Toolkit/Gateway as the only route to third-party MCP servers; `mcp-scan` in CI over the server list and `skills/`; Lasso MCP Gateway optional in front of the Docker gateway; tool descriptions pinned by hash in `tool_registry.health.description_hash` and a change raises an alert (rug-pull detection).

### 8.4 Input/output guards and redaction
- LLM Guard input scanners on user messages (prompt injection, secrets) and output scanners on tool results before they reach the model (prompt injection, malicious URLs); scanner verdicts logged on `tool_calls`; blocking is policy-configurable per case.
- Presidio replaces the regex redaction in `reports/redact.py` (en + hi recognisers where available; custom recognisers for wallets, fingerprints, onion locators); redaction map stored on the report.

### 8.5 Observability and evals
- Langfuse tracing for runs, tool calls and costs (trace id = run id); promptfoo nightly with both providers; dashboards for cost per thread, unverified-claim rate, policy denials, monitor lag.

### 8.6 Workers
- `arq` on Redis for ingest, extraction, embedding, monitoring and reports; `JobRunner` implementation swapped; API stays single-process for requests.

---

## M9 — Collector, sharing, front-ends, offline packaging

### 9.1 Live Tor collector
- Isolated service (`services/collector`) with the only Tor egress; policy file as in the v1 repo plan (GET/HEAD, no cookies, depth 1, 25 pages, 10 MiB, 6 rpm); source registry with encrypted locators and written authority; jobs pull from the API, push captures through `POST /cases/{id}/captures` (a new endpoint that runs `capture.gate` for the collector with `requester=SYSTEM`); bridges support for blocked networks.
- Acceptance: a registered, authorised onion source is captured on schedule; images quarantined; policy denials logged; the core product works with the collector disabled.

### 9.2 IntelOwl and OpenCTI/MISP
- IntelOwl connector: `identity-scout` and `chain-analyst` can submit observables to a local IntelOwl and capture the analyzer report; OpenCTI export: findings, entities and confirmed relationships as STIX 2.1 bundles (`GET /cases/{id}/export/stix`), with a mapping table and no guilt labels.

### 9.3 Second front-ends
- LibreChat or Open WebUI configured with a DARKNETRA MCP server (the same registry, role CASE_LEAD, service-token auth) for chat-only analysts; CopilotKit/AG-UI adapter in the Next.js app over the SSE stream.

### 9.4 Offline packaging
- A compose bundle with Postgres, the API, Ollama (qwen3:8b), SearXNG (keyless surface search inside the air-gap when a mirror exists), pre-downloaded models and the demo case; `scripts/package_offline.py` builds it; the walkthrough runs with `offline_mode=true` and passes the evidence-lane questions.

### 9.5 Harness alternatives
- Evaluate DeepSeek Harness or pi for an offline harness with local models; the registry adapters make the tool surface identical; keep the Claude harness as the online default.
