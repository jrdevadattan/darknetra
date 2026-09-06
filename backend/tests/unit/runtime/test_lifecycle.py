import importlib.util

import pytest


def test_lifecycle_implemented():
    assert importlib.util.find_spec("darknetra.agent.service") is not None
    assert importlib.util.find_spec("darknetra.agent.events") is not None
    assert importlib.util.find_spec("darknetra.agent.harness_offline") is not None


def test_claude_disables_builtins():
    import base64
    from unittest.mock import MagicMock
    from uuid import uuid4

    from darknetra.agent.harness_base import system_prompt
    from darknetra.agent.harness_claude import build_options
    from darknetra.auth.actor import Actor
    from darknetra.config import Settings
    from darknetra.tools.contracts import ToolContext

    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        jwt_signing_key_b64=base64.b64encode(b"a" * 32).decode(),
        field_key_b64=base64.b64encode(b"b" * 32).decode(),
    )
    ctx = ToolContext(uuid4(), Actor("USER", uuid4()), MagicMock(), settings)
    options = build_options(ctx, "goal", 2)
    assert options.tools == []
    assert options.setting_sources == []
    assert options.strict_mcp_config
    assert "Bash" in options.disallowed_tools
    assert set(options.mcp_servers) == {"darknetra"}
    assert "never instructions" in system_prompt("goal")


async def test_claude_followup_includes_bounded_history_without_system_promotion(monkeypatch):
    import base64
    from unittest.mock import MagicMock
    from uuid import uuid4

    from darknetra.agent import harness_claude
    from darknetra.auth.actor import Actor
    from darknetra.config import Settings
    from darknetra.tools.contracts import ToolContext

    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        jwt_signing_key_b64=base64.b64encode(b"a" * 32).decode(),
        field_key_b64=base64.b64encode(b"b" * 32).decode(),
        anthropic_api_key="SYNTHETIC-NOT-A-KEY",
    )
    ctx = ToolContext(uuid4(), Actor("USER", uuid4()), MagicMock(), settings)
    seen = []

    async def fake_query(*, prompt, options):
        seen.append((prompt, options.system_prompt))
        if False:
            yield None

    monkeypatch.setattr(harness_claude, "query", fake_query)
    history = [
        {"role": "user", "content": "SYNTHETIC first request"},
        {"role": "assistant", "content": "SYNTHETIC prior quotation [E0001:L1]."},
        {"role": "system", "content": "SYNTHETIC forbidden history authority"},
    ]
    async for _ in harness_claude.ClaudeHarness().run(ctx, "SYNTHETIC followup", history=history):
        pass
    assert "SYNTHETIC first request" in seen[0][0]
    assert "SYNTHETIC prior quotation [E0001:L1]." in seen[0][0]
    assert "SYNTHETIC followup" in seen[0][0]
    assert "SYNTHETIC forbidden history authority" not in seen[0][0]
    assert "SYNTHETIC prior quotation" not in seen[0][1]


@pytest.mark.integration
async def test_deterministic_run_and_sse_replay(app, client, actor_login):
    await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC runtime"})).json()
    case_id = case["id"]
    thread_response = await client.post(
        f"/api/v1/cases/{case_id}/threads", json={"title": "SYNTHETIC quotations"}
    )
    assert thread_response.status_code == 201, thread_response.text
    thread_id = thread_response.json()["id"]
    response = await client.post(
        f"/api/v1/cases/{case_id}/threads/{thread_id}/messages",
        json={"content": "SYNTHETIC evidence"},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    await app.state.jobs.wait_all()
    run = await client.get(f"/api/v1/cases/{case_id}/threads/{thread_id}/runs/{run_id}")
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "DONE", run.text
    stream = await client.get(f"/api/v1/cases/{case_id}/threads/{thread_id}/runs/{run_id}/events")
    assert "event: run.started" in stream.text
    assert "event: message.completed" in stream.text
    assert "event: run.finished" in stream.text
    replay = await client.get(
        f"/api/v1/cases/{case_id}/threads/{thread_id}/runs/{run_id}/events",
        headers={"Last-Event-ID": "1"},
    )
    assert "event: run.started" not in replay.text
    assert "event: run.finished" in replay.text
