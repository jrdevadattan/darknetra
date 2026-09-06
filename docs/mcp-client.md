# Use DARKNETRA from an MCP client

DARKNETRA provides a standalone stdio MCP server using the Python MCP SDK. It exposes the Case Lead tools from `darknetra.tools.registry`; newly registered tools appear without changing this adapter. This is separate from the Claude harness's in-process SDK bridge.

Run one server process per case. The server uses the same PostgreSQL database, vault, registry contracts, token authentication, case permissions, capture gate, and audit trail as the API. It does not start another HTTP endpoint, run the scheduler, or load arbitrary MCP servers or shell commands.

## Configure a case and token

Create a case-bound API token through the existing authenticated `POST /api/v1/auth/tokens` endpoint. Token creation uses the application's normal user session and CSRF protection. A minimal request is:

```json
{
  "name": "My case MCP client",
  "case_id": "<existing case UUID>",
  "scopes": ["cases:read", "threads:run"],
  "expires_in_days": 30
}
```

Supply the returned token using the MCP client's secret environment facility. Keep it out of command arguments, committed configuration, and chat messages. The two adapter settings are required environment variables:

| Variable | Value |
|---|---|
| `DARKNETRA_MCP_CASE_ID` | The existing case UUID bound to this process. |
| `DARKNETRA_MCP_API_TOKEN` | An unexpired, unrevoked `dk_` API token for an active account authorized for that case. |

The token owner must have permission to read evidence and run tools in the case. Additional actions still need their existing permissions and token scopes, such as `alerts:read` or `reports:generate`. Human decisions and unredacted exports are not made available by this adapter.

The ordinary application settings are also required, including `DARKNETRA_DATABASE_URL`, `DARKNETRA_VAULT_PATH`, and the existing encryption/signing keys. Use the restricted application database role. Application settings may come from the repository's uncommitted `.env`; the MCP binding and API token come from the process environment.

## Start the server

For the Docker deployment, run the MCP service through Compose. It shares the API's
database role and named vault volume; supply the binding variables in the client's
protected process environment:

```text
docker compose --env-file .env -f infra/docker-compose.yml run --rm -T --no-deps mcp
```

Use the repository as the client's working directory (or absolute paths for both
Compose files). Start PostgreSQL/API first. This starts one stdio server and opens
no network port. Do not connect a host MCP process to the Docker database with a
different local vault directory: the database and vault must describe the same
deployment.

From the repository root, after synchronizing the backend dependencies and migrating the database:

```text
uv run --project backend python -m darknetra.tools.adapters.stdio_mcp
```

The process waits for MCP JSON-RPC on stdin. Stdout is reserved for the protocol; startup errors go to stderr. A missing or invalid binding exits with status 2 and does not echo credentials.

For clients that accept a conventional `mcpServers` command configuration, use this template and replace the repository path. Provide the two binding variables through the client's protected environment configuration or inherited environment:

```json
{
  "mcpServers": {
    "darknetra-case": {
      "command": "uv",
      "args": [
        "--directory", "<absolute repository path>",
        "run", "--project", "backend",
        "python", "-m", "darknetra.tools.adapters.stdio_mcp"
      ]
    }
  }
}
```

The host command is for deployments where API and MCP already share a filesystem
vault. The explicit working directory resolves its application `.env` and relative
paths. Client configuration formats differ; the command and environment contract
above are supported. The adapter uses MCP SDK 2.x and was exercised with its actual
stdio client.

## What callers receive

`initialize` negotiates the SDK protocol, `tools/list` returns registry-derived input and output schemas, and `tools/call` invokes `tools.invoke`. Results contain a text JSON representation and matching `structuredContent`:

```json
{
  "ok": true,
  "data": {"...": "registered tool output"},
  "error": null,
  "evidence_ids": [],
  "truncated": false
}
```

Tool failures set MCP `isError` and carry a stable application error code. For example, network tools return `NETWORK_REQUIRED` in offline mode. Missing providers remain explicitly unavailable; listing a tool does not prove its provider is healthy. Large results return the existing bounded notice and evidence references.

No tool input can select another case. A supplied `case_id` is ignored by the shared invocation path, and every evidence query remains bound to the configured case. Unknown tools, including shell tool names, are rejected. Tools can write deterministic case records, captures, reports, and audit events; requests to the outside world remain subject to the existing GET/HEAD capture policy.

Authentication and case access are checked at startup and again for every catalogue or tool request. The invocation gate rechecks current user role, active/password state, session/token expiry and revocation, and case policy. Each request receives a new tool context so a previous result cache cannot bypass a later authorization or evidence-state change. An API or local offline setting disables network use.

Use returned evidence codes and spans when presenting claims. Captured text is source data, not instructions; link candidates are not confirmed findings. This server returns tool results. Prose generated by an external MCP client is not automatically stored as a verified DARKNETRA assistant message; use the application thread API when its persisted claim-checking workflow is required.

## Verification

```text
uv run --project backend pytest backend/tests/integration/test_stdio_mcp.py backend/tests/unit/test_stdio_mcp_cli.py -q
uv run --project backend mypy --config-file backend/pyproject.toml backend/darknetra/tools/adapters/stdio_mcp.py
```

The PostgreSQL integration test launches a real server subprocess through the MCP SDK's `stdio_client`, completes initialize/list/call, reads captured synthetic evidence, checks case isolation, exercises offline and unknown-tool failures, then revokes the token and checks the next call is denied. Additional tests reject an invalid token or foreign case binding and confirm missing/invalid startup settings leave stdout and credential values clean. Initial scoped result: **5 passed**, with only PGPy's existing `imghdr` deprecation warning; strict mypy passed.
