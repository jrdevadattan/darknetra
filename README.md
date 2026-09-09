# DARKNETRA — Codex CLI workspace

The `new-dev` branch is a local, single-user Next.js app. Cases and chats are saved in a JSON file; the app launches the installed Codex CLI directly with `codex exec --json` and resumes each chat's own Codex session. There is no FastAPI service, PostgreSQL database, custom agent SDK or evidence API. Docker is optional and includes the Python runtime used by the supplemental ML helper.

The frontend temporarily displays **Ollama**, as requested. This is branding only: no Ollama server or local Ollama model is used. The runtime and authentication remain Codex CLI.

Use the Settings gear at the top right to choose Light, Dark or System appearance. Dark keeps the green/charcoal palette; Light uses a pale green background. The choice persists in this browser.

Each chat has a three-dot menu with **Archive chat**. **Settings → Archived chats** lists saved chats with search, case names, archive dates, Open and Restore controls. Archiving keeps messages, uploads and assistant sessions intact; running replies and scheduled monitoring continue. Restore a chat before sending another message. Case-folder chevrons expand or collapse each folder independently and remember the choice in this browser.

**Netra** is selected with the eye button beside the composer. Give it a focused case objective, category, region or known reference. The Lead coordinates Surface Investigator and Dark Web Investigator, then an Evidence Reviewer checks corroboration and contradictions. Their actual activity and results appear in the existing timeline and graph. Reports distinguish advertisements and index entries from retrieved observations, and identify missing records without claiming a transaction or identity is proved.

A new Netra request in an existing chat clears only the previous native goal through the CLI's documented `thread/goal/clear` metadata command before creating the new goal. Conversation history and files remain intact; automatic passes resume the same session. The metadata helper uses local stdio with no model turn or listening server, requires the app's private `CODEX_HOME` (set by Docker), and does not use the operator's global configuration.

Netra enables native CLI goal tools backing [`/goal`](https://learn.chatgpt.com/use-cases/follow-goals). The pinned CLI's `exec` command exits after each turn, so the app resumes the exact session only while its persisted native goal remains active: at most six turns and ten minutes per request, with Stop available throughout. Goal status is read from that session's row in the CLI 0.153.4 state database (read-only); a missing/incompatible state remains unconfirmed. Existing normal/thinking chats and cron checks do not acquire this continuation loop. The lead shares a 60-page allowance across the team per user turn. The CLI site-review helper enforces its own page, depth, time and frontier limits; reads outside it still count against the shared allowance. Existing read-only tools remain primary and Apify remains backup. Netra cannot guarantee complete web coverage or the truth of a site's claims. Review source support and unresolved checks before acting on a report.

[Assistant instructions](frontend/assistant-instructions.md) set the case-focused investigative tone. The main assistant is Lead Investigator, with native CLI roles named Research Analyst, Records Analyst and File Examiner. Ordinary replies explain findings and uncertainty; actual operations stay visible in the activity panel. At most two specialists can run concurrently, one level deep. The prompt is loaded on each turn and mounted read-only in Docker, so wording changes apply without rebuilding.

Normal website reviews use the CLI `site-review` queue to follow explicit same-origin public links (default 30 pages, maximum 60, depth 4, three minutes and 250 retained frontier records). Results preserve individual sources, parent links, quoted review pointers and retrieved/failed/skipped/pending coverage. Page extraction preserves sibling articles, paragraph boundaries and declared text encodings. `page-section` and `page-links` expose remaining text and references, with response hashes and explicit truncation. JavaScript shells and access controls remain labelled gaps; no accounts, logins or form submissions are automated. These are bounded reviews, not complete website discovery. See [site review](frontend/skills/darknetra-osint/references/site-review.md).

The dedicated Telegram bot is used only for the explicitly requested configured group/channel. Docker loads private bot configuration from optional ignored `frontend/.env.local`. The CLI remains read-only: `telegram-read` returns an authenticated receipt, then the app's existing save process invokes the maintained CLI writer to verify and persist it. The writer makes no network requests; invalid receipts cannot advance the cursor. The activity entry confirms saved counts, while a pending receipt is labelled accordingly. `telegram-status` verifies the binding and permissions without consuming messages. The bot cannot export all historical messages or scrape arbitrary Telegram chats. See [Telegram setup](frontend/skills/darknetra-osint/references/telegram.md).

## Run

Install Node.js 22+ and Codex CLI, then sign in once with `codex login`.

```powershell
cd frontend
npm ci
npm run dev
```

Open [the local app](http://127.0.0.1:3000). For production: `npm run build`, then `npm start` from `frontend/`.

### Docker

From the repository root on Windows, with Docker Desktop running and Codex signed in:

```powershell
docker compose up --build -d
```

The UI is at http://127.0.0.1:3000. The container includes Codex CLI 0.153.4 and runs it directly. The separate `research` container runs Tor on the internal Docker network, without a published host SOCKS port. Both containers share the research image's ExifTool, Wireshark capinfos and YARA binaries. Codex executes the skill and binaries inside its own container; onion GET requests use `research:9050`. There is no remote command executor or Docker socket mount.

Existing local case/chat data remains in `frontend/.codex-chat`. The signed-in host auth file is supplied as a Docker secret, then copied to the container's persistent Codex home for token renewal; it is never included in the image. Set `CODEX_AUTH_FILE` to your `auth.json` path on non-Windows hosts or when using a custom Codex home. Stop with `docker compose down` (local data is retained). The separately deployed `darknetra-old` project is unaffected.

The app must run on the same computer as Codex. It binds to loopback and accepts only same-origin local writes. The tiny Next.js route bridge starts/stops the CLI and streams its JSON events; it is not a separate service. Codex uses a read-only sandbox, native web search and a separate working directory for each chat. Shell access lets Codex read and execute the bundled research skill. The app skips the operator's global Codex configuration; it adds no MCP server.

The CLI permission profile extends `:read-only` with network access for research. On Linux it selects the pinned CLI's Landlock compatibility sandbox because Docker's default seccomp profile blocks bubblewrap namespaces. It does not disable the sandbox or grant Docker privileges. This compatibility flag is deprecated upstream and must be rechecked before changing CLI versions. The helper enforces public destinations and GET-only reads; this is a local single-user research app, not a hardened multi-user sandbox for arbitrary untrusted shell commands.

## Specialists and scheduled monitoring

Sending a message opens a split view with conversation on the right and Agent activity on the left. The swap control remembers the preferred arrangement. Timeline keeps the Lead Investigator and actual specialists in separate cards with ordered, timestamped actions, public progress updates, results and status. View run opens the history for any earlier reply. On small screens the activity panel opens over the conversation and can be closed to return to chat.

Completed reviews switch to an interactive evidence graph connecting the lead, specialists, recorded checks, retrieved sources, attached files and report citations. Select a node for its excerpt, source URL, retrieval time or file hash; zoom, pan or expand the graph and browse its source list. Relationships describe provenance, not confirmed allegations. Index/feed/archive references stay unverified until separately retrieved. Report links without retrieval records are labelled accordingly. The graph is built deterministically from supported helper JSON and citations; ordinary shell output and private reasoning are never displayed. Earlier replies have only the history originally saved; no evidence is backfilled or invented.

Names come from the recorded child session after its parent is checked against the current chat. Collaboration v2 omits child IDs from some exec events, so the app also reads parent-verified child session metadata and public item/completion records. Encrypted assignments are shown by their recorded task name, without decrypting content. Unknown names use Case Specialist; an unconfirmed completion stays Unverified. Up to 300 activity entries per investigator and a bounded 1 MiB child-session tail are retained/read, with incomplete-history notices. Source excerpts are bounded to 1,500 characters; the graph is a working research map, not an immutable evidence archive.

Ask directly in chat, for example “Monitor this site every 15 minutes” or “Monitor this case daily at 09:00 UTC”. The app saves the schedule immediately and shows its actual status and next check in chat. No interval means hourly in the browser timezone. The current reply is the initial check; later checks use the same conversation, supplied files and CLI session. A general chat gets a case automatically. Repeating a request for the same target in that conversation updates the existing schedule. Questions, quotes, attachments and assistant output never create schedules. Unsupported intervals or ambiguous timezones show an explicit unscheduled notice. The clock button provides a time picker, selectable weekdays and minute intervals, plus pause/resume and Run now. It saves the matching cron expression internally; manually created schedules use a dedicated case chat. Stopping a reply does not pause its schedule.

The Next.js Node process starts the scheduler on server startup. Croner computes each schedule's next deadline; a five-second timer checks persisted deadlines and atomically claims due jobs before starting the same read-only CLI harness. The browser does not trigger jobs. Overlapping checks and busy conversations are skipped; the existing global three-chat execution limit applies. History records completion, errors, stops and skipped checks. Restarted checks are marked interrupted; missed times are advanced without replaying a backlog. Scheduling requires the app/container and computer to remain running and uses the connected account's model usage. Run only one app process per data directory.

Monitoring completions and failures appear in the notification bell. Settings → Push notifications enables browser Web Push, with disable, failures-only and test controls. Permission is requested only on that button click. Push messages contain a generic status and a link back to the case, never case titles, evidence or report text. Delivery uses the browser vendor's push service and can work with the tab closed; browser/OS background and notification settings still apply. The service worker caches no case content. Private VAPID keys and subscriptions persist separately in `.codex-chat/push-private.json` and are never returned by the workspace API. Expired subscriptions are removed; failed delivery leaves the update in the inbox. The inbox retains the latest 200 notifications; monitoring results remain in chat. Set `DARKNETRA_VAPID_SUBJECT` to your operator contact URI when appropriate. See [MDN's Push API documentation](https://developer.mozilla.org/en-US/docs/Web/API/Push_API) and the [web-push library](https://github.com/web-push-libs/web-push).

Cron expressions and timezone calculations use [Croner's documented scheduling API](https://croner.56k.guru/usage/examples/); specialist states use the [native exec collaboration events](https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs).

## CLI research skill

The supplied investigation methods are mapped to supported public-source and supplied-file reviews in `frontend/skills/darknetra-osint/references/investigation-methods.md`. Eight native roles are configured from `references/investigators.json`: Research Analyst, Records Analyst, File Examiner, Financial Analyst, Log Review Analyst, Postal Records Liaison, Case Liaison and Legal Liaison. Independent checks use the relevant specialists, with the existing two-specialist concurrency limit. Their actual activity and reports use the same timeline and evidence graph.

For unavailable or offline material, `references/records-requests.md` guides a case-specific next-leads response: needed records/fields, likely custodian and human route, case identifier and time range/timezone, purpose, suitable redacted upload format and an explicit unsent/awaiting state. New uploads are compared with the earlier gaps. Suggested requests do not become evidence and no department is contacted. The guide includes official MHA starting points for jurisdiction-specific human review; it does not invent legal authority or claim access to police, banking or commercial systems. Intrusive methods from the source document (including infiltration, covert purchases, exploitation, interception and deanonymization) are not implemented or planned.

Every chat, including resumed chats, gets a discoverable `.agents/skills/darknetra-osint` link to the maintained skill in `frontend/skills/darknetra-osint`. Ask naturally or name `$darknetra-osint`. Codex reads the skill and runs its Node helper itself; the UI shows the command activity and reply.

The helper supports Robin public-index search, public page reads, RSS/Atom feeds, Wayback snapshots, Tor connectivity verification, file hashes, ExifTool metadata, offline packet-file summaries and YARA matching with supplied rules. Native Codex web search handles surface discovery. Robin uses the MIT-derived parser from the original integration; Codex supplies the reasoning instead of a second Robin LLM. No evidence database, backend API or MCP is involved. Research instructions require actual status and relevant tool calls, with failures reported rather than invented results.

Docker supplies Tor automatically. Outside Docker, Robin needs a local Tor SOCKS proxy, default `socks5h://127.0.0.1:9050`; set `DARKNETRA_TOR_SOCKS_URL` for another local port. Public-web commands work independently of Tor. A challenge, timeout or unavailable provider returns a structured error, never a fabricated empty result. Index entries do not verify the target's existence or content.

The supplied list is recorded in [the tool catalogue](frontend/skills/darknetra-osint/references/tool-catalog.json). It is an availability inventory, not a claim that every entry is installed. Commercial services require separate accounts and licences; hardware requires an external workflow. Automated scanning, account enumeration, interception, face identification, password cracking and device unlocking are not integrated. `catalog <name>` explains each entry; `status` probes installed binaries.

Use the paperclip in the composer to attach up to 8 files per message, 32 MiB each. Uploads stay in `frontend/.codex-chat/inputs/<chat-id>/`, have unique filenames and are never overwritten. Sent attachments remain visible and downloadable after reload. Downloads and assistant inputs resolve only inside the selected chat. The CLI receives its own `DARKNETRA_INPUT_DIR` and attachment names automatically.

UTF-8 text is readable with `file-text` (16,000 characters per result, with truncation labelled). PNG, JPEG and WebP images are passed directly to the CLI image input. PDFs and other binary documents can be uploaded and inspected for metadata; full PDF/Office text extraction is not included. Files are never executed. Offline helper limits remain 256 KiB for self-contained YARA rules and 20 seconds per analysis; no live packet capture or sample execution is provided.

Image investigations run `metadata` on the original uploaded bytes. Results include grouped tags, readable findings, SHA-256, extractor warnings and explicit absence of capture-time/GPS tags. Filesystem/upload dates are excluded and embedded values remain unverified source claims. `page` also lists up to 40 explicit image references; `image-metadata <image-url>` reads one relevant public raster image up to 8 MiB through the validated GET transport (Tor for onion URLs). Remote bytes are processed in memory, not archived. The investigator's shared limit is five relevant remote images per turn; missing tags and failed checks remain distinct. Metadata source details preserve up to 16,000 characters. The Telegram text reader does not download image media; supply the original image attachment when needed.

Case folders offer **Create knowledge graph**. The board snapshots up to 36 recorded source/file/report cards from that case, including archived case conversations, with an explicit partial-coverage flag. **Generate with ImageGen** uses the built-in image generator through the same signed-in, read-only Codex CLI and includes up to three eligible supplied image references. It does not require a separate image API key. The generated image is an illustrated overview, not evidence; review it against the clickable original source cards. Native output is collected only from `generated_images/<actual CLI thread ID>/`, copied to content-addressed local board storage, and served through case-checked routes. Generated images can be downloaded and reopened after refresh. Regeneration preserves previous board snapshots and original files. A generation failure remains a visible failure; the source-card view is never labelled an ImageGen result.

To use the helper directly from `frontend/`:

```powershell
node skills/darknetra-osint/scripts/osint.mjs status
node skills/darknetra-osint/scripts/osint.mjs robin 'Tor Project' 5
node skills/darknetra-osint/scripts/osint.mjs page 'https://example.com'
```

To check the Docker tools from the repository root:

```powershell
docker compose exec -T research node skills/darknetra-osint/scripts/osint.mjs tor-check
docker compose exec -T research node research/smoke.mjs
```

## Configuration and data

Copy `.env.example` to `frontend/.env.local` if overrides are needed. `CODEX_BIN` selects a native Codex executable, `CODEX_MODEL` optionally selects a model, and `CODEX_CHAT_DATA_DIR` changes local storage. No API key is required when Codex is signed in with ChatGPT.

Cases, messages and activity are stored in `frontend/.codex-chat/workspace.json` by default. Native Codex sessions stay in the signed-in Codex home; keep those files to retain session resume. Reloading the browser reconnects to running replies. Stop terminates the current CLI process; runs have a ten-minute timeout. Run a single app process against each data directory.

Existing investigation databases and vaults are not imported or erased. The former backend, deployment scripts and UI were preserved locally under `.git/legacy-backup-20260908-122158/` before removal from this branch. Historical plans in `docs/` describe the previous architecture, not this branch's runtime.

## Checks

```powershell
cd frontend
npm test
npm run typecheck
npm run build
npm run test:e2e
```

Browser tests launch an isolated app on port 3100 with temporary SYNTHETIC data. They make real Codex CLI calls using the signed-in account and check skill execution, resume, case isolation and cancellation.

[Official Codex non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) describes the CLI event stream and session resume used here.
[Official Codex skill documentation](https://learn.chatgpt.com/docs/build-skills) describes the local skill discovery used here.
[Official Codex permission documentation](https://learn.chatgpt.com/docs/permissions) describes read-only profiles, network access and Linux compatibility fallbacks.
