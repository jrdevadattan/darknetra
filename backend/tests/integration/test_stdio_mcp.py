"""A real SDK stdio client reaches the registry through a case-bound API token."""

import importlib.util
import os
import sys
from pathlib import Path
from uuid import UUID

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from sqlalchemy import select

from darknetra.audit.models import AuditEvent
from darknetra.tools.contracts import AgentRole
from darknetra.tools.registry import for_role


def test_stdio_adapter_exists():
    assert importlib.util.find_spec("darknetra.tools.adapters.stdio_mcp") is not None


async def test_real_sdk_stdio_handshake_calls_isolation_and_revocation(client, actor_login, app):
    assert importlib.util.find_spec("darknetra.tools.adapters.stdio_mcp") is not None
    await actor_login()
    first = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC MCP first", "demo": True})
    ).json()
    second = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC MCP second", "demo": True})
    ).json()
    for case, text in [
        (first, b"SYNTHETIC_MCP_FIRST quoted evidence"),
        (second, b"SYNTHETIC hiddenothercasemarker private fixture"),
    ]:
        response = await client.post(
            f"/api/v1/cases/{case['id']}/evidence",
            files={"files": ("SYNTHETIC.txt", text)},
            data={"source_class": "SYNTHETIC"},
        )
        assert response.status_code == 201
    await app.state.jobs.wait_all()
    response = await client.post(
        "/api/v1/auth/tokens",
        json={
            "name": "SYNTHETIC MCP",
            "case_id": first["id"],
            "scopes": ["cases:read", "threads:run"],
        },
    )
    assert response.status_code == 201
    credential = response.json()
    settings = app.state.settings
    environment = {
        **os.environ,
        "DARKNETRA_DATABASE_URL": settings.database_url,
        "DARKNETRA_VAULT_PATH": str(settings.vault_path),
        "DARKNETRA_JWT_SIGNING_KEY_B64": settings.jwt_signing_key_b64.get_secret_value(),
        "DARKNETRA_FIELD_KEY_B64": settings.field_key_b64.get_secret_value(),
        "DARKNETRA_OFFLINE_MODE": "true",
        "DARKNETRA_SCHEDULER_ENABLED": "false",
        "DARKNETRA_MCP_CASE_ID": first["id"],
        "DARKNETRA_MCP_API_TOKEN": credential["token"],
    }
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "darknetra.tools.adapters.stdio_mcp"],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
    )
    async with (
        stdio_client(server) as (read, write),
        ClientSession(read, write, read_timeout_seconds=30) as connection,
    ):
        initialized = await connection.initialize()
        assert initialized.server_info.name == "darknetra"
        tools = (await connection.list_tools()).tools
        assert {tool.name for tool in tools} == {
            spec.name for spec in for_role(AgentRole.CASE_LEAD)
        }
        search = next(tool for tool in tools if tool.name == "search_evidence")
        assert "query" in search.input_schema["properties"]
        assert "case_id" not in search.input_schema["properties"]
        assert search.output_schema["properties"]["data"]["anyOf"][0]["properties"]["hits"]
        found = await connection.call_tool("search_evidence", {"query": "SYNTHETIC_MCP_FIRST"})
        assert not found.is_error and found.structured_content["ok"]
        assert found.structured_content["data"]["hits"]
        hidden = await connection.call_tool(
            "search_evidence", {"query": "hiddenothercasemarker", "case_id": second["id"]}
        )
        assert not hidden.is_error and not hidden.structured_content["data"]["hits"]
        denied = await connection.call_tool(
            "fetch_page", {"url": "https://synthetic.example.invalid/"}
        )
        assert denied.is_error and denied.structured_content["error"]["code"] == "NETWORK_REQUIRED"
        unknown = await connection.call_tool("Bash", {"command": "ignored"})
        assert unknown.is_error and unknown.structured_content["error"]["code"] == "VALIDATION"
        assert (await client.delete("/api/v1/auth/tokens/" + credential["id"])).status_code == 204
        revoked = await connection.call_tool("search_evidence", {"query": "SYNTHETIC_MCP_FIRST"})
        assert revoked.is_error and revoked.structured_content["error"]["code"] == "UNAUTHENTICATED"
        assert credential["token"] not in str(revoked)
    async with app.state.session_factory() as db:
        events = list(
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.case_id == UUID(first["id"]), AuditEvent.action == "tool.call"
                )
            )
        )
        assert len(events) >= 4


async def test_invalid_token_or_other_case_cannot_bind(client, actor_login, app):
    from pydantic import SecretStr

    from darknetra.errors import NotFound, Unauthenticated
    from darknetra.tools.adapters.stdio_mcp import create_server

    await actor_login()
    first = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC MCP credential case"})
    ).json()
    second = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC MCP other case"})).json()
    response = await client.post(
        "/api/v1/auth/tokens",
        json={
            "name": "SYNTHETIC MCP",
            "case_id": first["id"],
            "scopes": ["cases:read", "threads:run"],
        },
    )
    import pytest

    with pytest.raises(Unauthenticated):
        await create_server(
            app.state.session_factory,
            app.state.settings,
            UUID(first["id"]),
            SecretStr("dk_SYNTHETIC_INVALID"),
        )
    with pytest.raises(NotFound):
        await create_server(
            app.state.session_factory,
            app.state.settings,
            UUID(second["id"]),
            SecretStr(response.json()["token"]),
        )
