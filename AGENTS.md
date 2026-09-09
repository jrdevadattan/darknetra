# AGENTS.md — new-dev

This branch is the user's requested standalone Codex CLI chat workspace.
The previous backend plan in docs/implementation-plan.md is historical on this branch.

- Run the Next.js app in frontend/. It launches the installed Codex CLI directly.
- Keep case/chat persistence simple and local; do not restore FastAPI, PostgreSQL or the evidence pipeline.
- Keep CLI prompts on stdin, never interpolate them into shell commands.
- Preserve loopback/same-origin checks, read-only execution and per-chat session isolation.
- Do not load the operator's global plugins, hooks or MCP configuration into web chats.
- Research tools live in frontend/skills/darknetra-osint. Codex discovers the skill per chat and executes its read-only CLI helpers directly; do not turn it into an MCP or backend service.
- User-requested Apify exception: the CLI skill calls the official MCP for catalog search and Actor details only. Public-page execution stays in the bounded CLI backup adapter; Robin and existing readers remain primary. Never enable arbitrary Actor execution or account-wide storage access.
- Never delete existing investigation data or backups when cleaning up code.
- Label test fixtures SYNTHETIC. Keep credentials and local chat data out of Git.
- Verify with npm test, npm run typecheck and npm run build in frontend/.

## Remembered Telegram integration preference

- The user plans to provide access to a Telegram bot for Darknetra and states they administer the target group/channel. Prefer this bot for collecting future messages from explicitly selected chats.
- The dedicated bot reader is implemented in the existing CLI skill as `telegram-status` and `telegram-read <configured-chat-id>`. It runs on demand, not as a background collector. Bot token and chat binding are in ignored local environment configuration; do not copy their values here.
- Keep the bot token in ignored local credential storage; never put it in project instructions, chat prompts, logs or Git. Do not use a personal Telegram session for this integration.
- The standard Bot API does not provide full historical chat retrieval. Preserve local persistence and per-chat isolation, and do not send messages or modify group/channel settings without explicit authorization.
