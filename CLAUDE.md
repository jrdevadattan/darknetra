# AGENTS.md — new-dev

This branch is the user's requested standalone Codex CLI chat workspace.
The previous backend plan in docs/implementation-plan.md is historical on this branch.

- Run the Next.js app in frontend/. It launches the installed Codex CLI directly.
- Keep case/chat persistence simple and local; do not restore FastAPI, PostgreSQL or the evidence pipeline.
- Keep CLI prompts on stdin, never interpolate them into shell commands.
- Preserve loopback/same-origin checks, read-only execution and per-chat session isolation.
- Do not load the operator's global plugins, hooks or MCP configuration into web chats.
- Never delete existing investigation data or backups when cleaning up code.
- Label test fixtures SYNTHETIC. Keep credentials and local chat data out of Git.
- Verify with npm test, npm run typecheck and npm run build in frontend/.
