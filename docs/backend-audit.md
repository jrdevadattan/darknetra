# Backend completion audit — 6 September 2026

The audit compared the implementation overview, every plan under `docs/plan/`, the
current source and the acceptance tests. This is a status record, not a declaration
that the entire M0–M9 roadmap or production deployment is complete.

## Completed in this increment

| Operation | Before | Current behavior |
|---|---|---|
| Semantic/hybrid retrieval (M2) | Always lexical | Local Sentence Transformers loader; validated normalized 1024-dimensional vectors; atomic per-evidence embedding batches; matching-model coverage checks; pgvector semantic ranking and RRF hybrid fusion; explicit lexical fallback. |
| Reindex existing evidence (M2) | No operator command | `backend/scripts/reindex.py --case-id UUID --actor-id UUID` verifies operator access, retains evidence/chunk identity and audits index updates. |
| Office uploads and PDF locations (M1) | Office blanket-quarantined; PDF page map absent | Passive bounded DOCX/XLSX/PPTX extraction, package checks, preserved paragraph whitespace, sheet/slide relationship order, and exact LF line maps including blank PDF pages. Originals remain unchanged. |
| NVIDIA NIM (M3) | No adapter | OpenAI-compatible chat completions; registered role tools, bounded requests/responses, finite pricing required, preflight USD allowance, usage validation and inherited worker/case restrictions. |
| Private normal chats | Case ID required everywhere | Separate owner-scoped tables and `/chats` routes; tool-free Claude/NIM/Ollama; persisted runs/messages/SSE; cancellation, restart recovery and explicit unavailable results. Case access does not confer private-chat access. |
| Reviewed plugins | Static tool catalog only | Catalog with implementation/lockfile manifest hashes, administrator enable/disable and case allowlist. Invocation rechecks state even for cached results; provider/MCP catalogs omit disabled integrations. Arbitrary executables are not installed. |
| Search monitoring | Raw search-page captures could count as hits | Uses parsed surface/Robin result entries; only matching entries count; all entries from an index share a source family. Index entries do not claim target pages were fetched. |
| Monitoring authority | Revoked creator silently stopped work | Persisted failed monitor run, suspension reason, audited denial and bounded operational alert. It does not borrow another person's permissions. Restore authority or create a replacement item under an authorised operator. |
| Provider retry state | Only next item time | Per-source persisted backoff; healthy sources can continue; repeated failures and retry deferrals remain visible. |
| Monitor interruption (M6) | Attempts existed only after collection finished | A running attempt and audit event are committed before collection. Cancellation/failure closes the attempt with an error; startup recovery marks orphaned attempts and schedules a retry. Active collectors are protected by advisory locks, and current operator authority is rechecked before results are published. |
| Thread memory | Summary fields never written | Every six assistant messages, stores a bounded extractive memory of the last twelve user requests with source message IDs. It is conversation context, not evidence or new model-written facts. |
| Case digest | Missing endpoint | Case-scoped `/digest?since=` with current pending-pair counts, up to ten open alerts and ten recent findings; access and audit apply. |
| Evidence reader lines | Form-feeds shifted tool line numbers away from stored citations | Reader uses the same LF line convention as derivative offsets, extraction and context lookup. |
| Small-charge accounting | Charges could round to zero | Budget accounting rounds upward to four decimal places; less than USD 0.0001 excess per recorded charge, rather than silently discarding positive charges. This is a budget reserve, not a provider invoice. |
| CI/CD | Pipelines on main/dev and legacy jobs | Main/dev workflows removed and pushed; production retains only `production.yml` with production-only jobs. No deployment was requested or performed. |

## Configuration required for live acceptance

- **Dense model:** install the optional `embed` runtime and provision a local
  1024-dimensional Sentence Transformers model directory. The service neither downloads
  weights during requests nor runs model repository code. Set
  `DARKNETRA_EMBEDDING_BACKEND=sentence_transformers` and
  `DARKNETRA_EMBEDDING_MODEL_PATH`. Model identity hashes local contents; replace assets
  through a new directory and restart before reindexing. The default remains `none`.
  Host: `uv sync --project backend --extra embed`. Docker: build the API with
  `--build-arg DARKNETRA_EMBEDDINGS=1`, provision its models volume, and use a container
  path under `/app/models/cache`. The default Docker image omits heavyweight models.
- **NIM:** set base URL (ending in `/v1`), model, optional worker model and API key
  when required by the deployment. Set both per-million input/output prices; explicit
  zero prices are reserved for a free deployment. Select `DARKNETRA_HARNESS_MODE=nim`
  and disable offline mode to use it. Self-hosted NIM may be keyless. A consumer login
  subscription is not used as an API credential.
- **Claude/Ollama:** live credentials or a reachable installed local model are required.
  Private chats in the deterministic demonstration return unavailable, not fake answers.
- **Search:** a reliable configured public HTTPS SearXNG provider is still needed for
  repeatable live acceptance. Earlier public search diagnostics were unavailable/rate
  limited. Adapter tests do not establish external service reliability.

Local model loading follows [Sentence Transformers' documented local-files mode](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html).
NIM uses [NVIDIA's chat-completions protocol](https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html).

## Unfinished roadmap operations

These are retained as explicit gaps. No empty successful response is substituted for them.

| Area | Remaining dependency or implementation |
|---|---|
| Extraction | Trained NER, OCR/transcription assets and integration; visual layout/reading-order reconstruction and full precedence pipeline. Office text and PDF page maps are implemented; DOCX rendered pages, spreadsheet formatting/formula evaluation, presentation notes and embedded media are not reconstructed. |
| Analytics | Trained GNN assets, verified sanctions-feed ingestion, image-to-author ownership, price/unit normalization and near-duplicate families. |
| External monitoring | Isolated Tor collector; supported Telegram/identity/ETH/TRON adapters; authority/source setup and live acceptance. Person lookup remains policy denied. |
| Durable orchestration | Independently resumable/parallel workers, external queue, multi-process scheduling and provider-session resume. Current deployment uses one API process. |
| Plugin installation | Sandboxed third-party MCP installation, remote gateway lifecycle, signing/scanning and version upgrades. Current controls govern the integrations shipped with the backend. |
| Sharing and exports | Membership-based online case access exists. Hermes messaging, Codex analyst integration, STIX/OpenCTI and additional sharing surfaces remain M7–M9. |
| Evaluation | Live provider holdouts, OCR/NER/GNN quality, full scenario/performance coverage and production-scale benchmarks. Synthetic vector tests establish mechanics, not semantic quality. |
| Frontend | Implementation remains explicitly out of scope; root `frontend.md` contains the integration contract and researched UI projects. |

The current migration is `0003_workspace_completion`; it adds four private-chat tables,
append-only message/event enforcement and NIM checks without altering applied migrations.
Private-provider values are validated at API/runtime boundaries; additional database
provider-enum checks require a later migration. API additions are captured in OpenAPI.

The final verification results are recorded in `build-progress.md`.

Office parsing accepts at most 2,000 archive members, 100 MiB declared expanded
content, 20 MiB per parsed XML part and 5 million budgeted text characters.
Unsafe members, duplicate paths, encrypted archives and XML entity declarations are
rejected. It never extracts packages to disk, fetches external relationships or runs
active content. XLSX exposes stored values, which can include stale cached formula
results; it does not recalculate them. PDF derived text places form-feed separators
between LF boundaries so page maps and existing citation lines use the same convention.
