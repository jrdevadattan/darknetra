# Codex CLI workspace

See [the root README](../README.md) for setup, storage and CLI configuration.

Run `npm run dev` in this directory and open http://127.0.0.1:3000. Only Node.js and a signed-in Codex CLI are needed. The Next.js routes launch Codex directly; no separate API server is used.
# Apify backup

Apify catalog search and Actor input/pricing lookup are available to the app's Codex CLI through the official MCP. Robin, native web search and the existing readers stay primary. Catalog results are candidate integrations; the current executable adapter is a bounded public-page backup in the OSINT skill. It runs only for an explicit request or a failed/incomplete ordinary read.

Set `apify` in the ignored `.codex-chat/providers.json`, preserving existing provider entries. See [the Apify reference](skills/darknetra-osint/references/apify.md) for commands, scope and limits. Credentials stay outside Git and browser storage.
