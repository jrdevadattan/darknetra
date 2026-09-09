# Telegram — dedicated bot reader

Use only when the user explicitly requests messages from the configured group/channel. This is the user's bot integration, separate from Apify. It uses Telegram's official Bot API with a local bot token, never a personal login, OTP or user session.

```sh
node .agents/skills/darknetra-osint/scripts/osint.mjs telegram-status
node .agents/skills/darknetra-osint/scripts/osint.mjs telegram-read '<configured-negative-chat-id>'
```

`telegram-status` verifies bot identity, webhook state, membership and the chat binding, and returns the configured chat ID, title, type and public username when available. It does not consume updates. Match a requested public Telegram link against that username, or use the exact configured ID when the user explicitly asks for their configured chat. If the source cannot be matched, ask which source they mean before reading messages. If ordinary-message access is false, tell the operator the bot needs appropriate group permissions or disabled privacy mode; do not change these settings yourself.

`telegram-read` requires the exact configured ID and refuses other chats. It requests at most 100 pending bot updates, saves only that target's message and edit events, and returns the latest 20 saved events with explicit text truncation. The full JSON archive lives in the ignored `frontend/.codex-chat/telegram/` directory. This operator source archive is shared for the one configured Telegram target; it does not read any Codex conversation's history. Only use it in a case whose user has requested this source. Do not read unrelated case files or expose the archive to other cases automatically.

The durable cursor advances only after successful storage. In web chats the CLI stays read-only: the reader returns an authenticated capture receipt with `pendingStorage: true`, and the app's existing save process invokes the internal CLI writer to verify and commit it. The activity entry confirms saved counts. Do not claim storage succeeded from a pending receipt. Collection stays in the CLI; the writer makes no network requests. A directory lock and serial save queue prevent competing writes. Invalid receipts, active webhooks, corrupt archives, different chat bindings and archives over 16 MiB fail closed without deleting data. If interrupted, inspect any remaining lock before removing it. Other chats' update contents are discarded; only their update IDs remain for the dedicated cursor. This integration is for one chat per bot.

The lead runs Telegram collection directly, sequentially. Specialists receive the relevant collected excerpts for review and do not start competing bot readers. If a full batch indicates more pending updates, the lead may run one further sequential read for the requested check. Never treat a failed save or unread backlog as complete coverage.

Collection runs only when the command runs. Telegram retains undelivered bot updates for at most 24 hours, so long gaps or a backlog larger than one batch can cause missed messages. A full batch sets `moreUpdatesMayBePending`; another explicit read can fetch the next batch. Do not claim background monitoring is active without a separately created schedule. Existing app schedules may call this same bounded helper when the user requests monitoring.

Only available text/captions and basic message metadata are saved. Media is not downloaded, deleted messages cannot be recovered, and edits remain separate events. A zero-result read does not mean the group has no messages. The bot cannot export history from before it had access. If receipt needs testing, ask the user to send a new `/darknetra_test@<bot-username>` command in the target chat; never send it yourself.

## Operator setup

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in ignored `frontend/.env.local`. Never print the token or put it in prompts, command arguments, URLs shown to users or Git. Telegram requires the token in API URL paths internally; the helper suppresses raw network errors and refuses redirects. Restart the Next.js app after changing environment configuration so new CLI sessions inherit it.

For a standalone terminal, from `frontend/` use:

```sh
node --env-file=.env.local skills/darknetra-osint/scripts/osint.mjs telegram-status
node --env-file=.env.local skills/darknetra-osint/scripts/osint.mjs telegram-read '<configured-negative-chat-id>'
```

Docker Compose reads this optional environment file when creating the UI container; recreate the UI after changing it. The app sets `DARKNETRA_TELEGRAM_READ_ONLY=1` for web-chat CLI sessions. Keep this setting: collection returns signed receipts and the app persists them using the maintained writer. No extra filesystem permission, Docker privilege, service or MCP is required. Standalone terminal reads retain the existing direct archive writer. Do not edit the archive or invoke the internal commit entrypoint yourself.

The token may alternatively be supplied through the process environment. Keep this reader as a CLI skill; no MCP, backend service or unrestricted Telegram client is needed.

Official references: [Bot API updates](https://core.telegram.org/bots/api#getupdates), [message visibility](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get).
