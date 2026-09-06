import pytest

from darknetra.chats.providers import normal_chat_prompt, select_provider
from darknetra.errors import Unavailable


async def test_deterministic_never_fakes_an_answer(test_settings):
    with pytest.raises(Unavailable):
        await select_provider("DETERMINISTIC", test_settings)


async def test_explicit_missing_nim_does_not_fallback(test_settings):
    with pytest.raises(Unavailable):
        await select_provider("NIM", test_settings)


def test_normal_prompt_has_no_case_authority():
    assert "no access" in normal_chat_prompt()


async def test_owner_isolation_and_honest_unavailable(client, actor_login, app):
    await actor_login()
    response = await client.post(
        "/api/v1/chats", json={"title": "SYNTHETIC private", "provider": "DETERMINISTIC"}
    )
    assert response.status_code == 201, response.text
    chat = response.json()["id"]
    response = await client.post(
        f"/api/v1/chats/{chat}/messages", json={"content": "SYNTHETIC hello"}
    )
    assert response.status_code == 202, response.text
    run = response.json()["run_id"]
    await app.state.jobs.wait_all()
    result = await client.get(f"/api/v1/chats/{chat}/runs/{run}")
    assert result.json()["error"]["code"] == "UNAVAILABLE"
    assert result.json()["cost_complete"] is False
    messages = await client.get(f"/api/v1/chats/{chat}/messages")
    assert len(messages.json()["items"]) == 1
    events = await client.get(f"/api/v1/chats/{chat}/runs/{run}/events")
    assert "run.finished" in events.text
    await actor_login(role="ADMIN")
    for path in [
        f"/chats/{chat}",
        f"/chats/{chat}/messages",
        f"/chats/{chat}/runs/{run}",
        f"/chats/{chat}/runs/{run}/events",
    ]:
        assert (await client.get("/api/v1" + path)).status_code == 404
    assert (await client.post(f"/api/v1/chats/{chat}/runs/{run}/cancel")).status_code == 404


@pytest.mark.parametrize("provider", ["NIM", "OFFLINE"])
async def test_tool_free_http_transport(provider, test_settings, respx_mock):
    import json
    from decimal import Decimal

    import httpx
    from pydantic import SecretStr

    from darknetra.chats.providers import generate

    settings = test_settings.model_copy(
        update={
            "offline_mode": False,
            "nim_base_url": "https://synthetic.invalid/v1",
            "nim_model": "SYNTHETIC",
            "nim_api_key": SecretStr("SYNTHETIC"),
            "nim_input_cost_per_million": 1,
            "nim_output_cost_per_million": 1,
        }
    )
    url = (
        "https://synthetic.invalid/v1/chat/completions"
        if provider == "NIM"
        else settings.ollama_url + "/api/chat"
    )
    payload = (
        {
            "choices": [{"message": {"content": "SYNTHETIC answer"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }
        if provider == "NIM"
        else {"message": {"content": "SYNTHETIC answer"}, "prompt_eval_count": 10, "eval_count": 2}
    )
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=payload))
    result = [
        event
        async for event in generate(
            provider, settings, [{"role": "user", "content": "SYNTHETIC hi"}], Decimal("2")
        )
    ]
    body = json.loads(route.calls.last.request.content)
    assert "tools" not in body and "tool_choice" not in body
    assert result[0]["text"] == "SYNTHETIC answer"
    assert result[-1]["cost_complete"] is True


async def test_nim_rejects_tool_call(test_settings, respx_mock):
    from decimal import Decimal

    import httpx
    from pydantic import SecretStr

    from darknetra.chats.providers import generate
    from darknetra.errors import PolicyDenied

    settings = test_settings.model_copy(
        update={
            "nim_base_url": "https://synthetic.invalid/v1",
            "nim_model": "SYNTHETIC",
            "nim_api_key": SecretStr("SYNTHETIC"),
            "nim_input_cost_per_million": 1,
            "nim_output_cost_per_million": 1,
        }
    )
    respx_mock.post("https://synthetic.invalid/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [{"function": {"name": "case_search"}}],
                        }
                    }
                ]
            },
        )
    )
    with pytest.raises(PolicyDenied):
        _ = [event async for event in generate("NIM", settings, [], Decimal("2"))]


async def test_private_lifecycle_success_resume_cancel_recovery(
    client, actor_login, app, monkeypatch
):
    import asyncio
    from decimal import Decimal
    from uuid import uuid4

    from darknetra.api.v1.routes.chats import owner_actor
    from darknetra.auth.actor import Actor
    from darknetra.chats import providers, service

    user = await actor_login()

    async def select(*args):
        return "OFFLINE"

    async def generate(*args):
        yield {"type": "assistant", "text": "SYNTHETIC assistant"}
        yield {
            "type": "usage",
            "cost_usd": Decimal("0"),
            "tokens_in": 1,
            "tokens_out": 1,
            "cost_complete": True,
        }

    monkeypatch.setattr(providers, "select_provider", select)
    monkeypatch.setattr(providers, "generate", generate)
    chat = (await client.post("/api/v1/chats", json={"title": "SYNTHETIC lifecycle"})).json()["id"]
    path = f"/api/v1/chats/{chat}"
    run = (await client.post(path + "/messages", json={"content": "SYNTHETIC hello"})).json()[
        "run_id"
    ]
    await app.state.jobs.wait_all()
    assert (await client.get(path + f"/runs/{run}")).json()["status"] == "DONE"
    messages = (await client.get(path + "/messages")).json()["items"]
    assert messages[-1]["verification"]["mode"] == "NOT_APPLICABLE"
    events = (await client.get(path + f"/runs/{run}/events", headers={"Last-Event-ID": "1"})).text
    assert "event: run.started" not in events and "event: run.finished" in events

    async def waiting(*args):
        await asyncio.sleep(60)
        yield {}

    monkeypatch.setattr(providers, "generate", waiting)
    run2 = (await client.post(path + "/messages", json={"content": "SYNTHETIC waiting"})).json()[
        "run_id"
    ]
    assert (
        await client.post(path + "/messages", json={"content": "SYNTHETIC duplicate"})
    ).status_code == 409
    assert (await client.post(path + f"/runs/{run2}/cancel")).status_code == 202
    assert (await client.get(path + f"/runs/{run2}")).json()["status"] == "CANCELLED"
    from uuid import UUID

    async with app.state.session_factory() as db:
        abandoned = await service.post_message(db, user.id, UUID(chat), "SYNTHETIC interrupted")
    await service.recover_interrupted(app.state.session_factory)
    assert (await client.get(path + f"/runs/{abandoned.id}")).json()["status"] == "ERROR"
    from darknetra.errors import Forbidden

    with pytest.raises(Forbidden):
        await owner_actor(Actor("TOKEN", uuid4(), user_id=user.id))


async def test_claude_options_are_tool_free(test_settings, monkeypatch):
    from decimal import Decimal

    import claude_agent_sdk as sdk
    from pydantic import SecretStr

    from darknetra.chats.providers import generate

    seen = {}

    async def fake_query(*, prompt, options):
        seen["options"] = options
        yield sdk.AssistantMessage(
            content=[sdk.TextBlock(text="SYNTHETIC answer")], model="SYNTHETIC"
        )
        yield sdk.ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="SYNTHETIC",
            total_cost_usd=0.01,
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(sdk, "query", fake_query)
    settings = test_settings.model_copy(update={"anthropic_api_key": SecretStr("SYNTHETIC")})
    result = [event async for event in generate("CLAUDE", settings, [], Decimal("2"))]
    options = seen["options"]
    assert options.tools == [] and options.allowed_tools == [] and options.mcp_servers == {}
    assert options.skills == [] and options.plugins == [] and options.setting_sources == []
    assert options.strict_mcp_config is True
    assert result[-1]["cost_complete"] is True


async def test_nim_unknown_pricing_does_not_spend(test_settings, respx_mock):
    from decimal import Decimal

    from darknetra.chats.providers import generate

    with pytest.raises(Unavailable):
        _ = [event async for event in generate("NIM", test_settings, [], Decimal("2"))]
    assert len(respx_mock.calls) == 0


@pytest.mark.parametrize("provider", ["SYNTHETIC_UNKNOWN", "", "nim"])
async def test_unknown_provider_never_falls_back(provider, test_settings, respx_mock):
    from decimal import Decimal

    from darknetra.chats.providers import generate

    with pytest.raises(Unavailable):
        await select_provider(provider, test_settings)
    with pytest.raises(Unavailable):
        _ = [event async for event in generate(provider, test_settings, [], Decimal("2"))]
    assert not respx_mock.calls


async def test_subprecision_costs_exhaust_chat_budget(client, actor_login, app, monkeypatch):
    from decimal import Decimal

    from darknetra.chats import providers

    await actor_login()

    async def selected(*args):
        return "OFFLINE"

    async def generated(*args):
        yield {
            "type": "usage",
            "cost_usd": Decimal("0.000001"),
            "tokens_in": 1,
            "tokens_out": 1,
            "cost_complete": True,
        }

    monkeypatch.setattr(providers, "select_provider", selected)
    monkeypatch.setattr(providers, "generate", generated)
    chat = (
        await client.post(
            "/api/v1/chats", json={"title": "SYNTHETIC tiny budget", "budget_usd": "0.0002"}
        )
    ).json()["id"]
    path = f"/api/v1/chats/{chat}"
    for _ in range(2):
        assert (
            await client.post(path + "/messages", json={"content": "SYNTHETIC tiny cost"})
        ).status_code == 202
        await app.state.jobs.wait_all()
    assert (
        await client.post(path + "/messages", json={"content": "SYNTHETIC exhausted"})
    ).status_code == 402
    assert Decimal((await client.get(path)).json()["spent_usd"]) == Decimal("0.0002")


async def test_cancellation_is_persisted_before_resistant_provider_finishes(
    client, actor_login, app, monkeypatch
):
    import asyncio

    from darknetra.chats import providers

    await actor_login()
    started, release = asyncio.Event(), asyncio.Event()

    async def selected(*args):
        return "OFFLINE"

    async def generated(*args):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        yield {"type": "assistant", "text": "SYNTHETIC late answer"}

    monkeypatch.setattr(providers, "select_provider", selected)
    monkeypatch.setattr(providers, "generate", generated)
    chat = (await client.post("/api/v1/chats", json={"title": "SYNTHETIC resistant"})).json()["id"]
    path = f"/api/v1/chats/{chat}"
    run = (await client.post(path + "/messages", json={"content": "SYNTHETIC request"})).json()[
        "run_id"
    ]
    await asyncio.wait_for(started.wait(), 5)
    try:
        async with asyncio.timeout(3):
            response = await client.post(path + f"/runs/{run}/cancel")
        assert response.status_code == 202
        state = (await client.get(path + f"/runs/{run}")).json()
        assert state["status"] == "CANCELLED" and state["cost_complete"] is False
    finally:
        release.set()
        await app.state.jobs.wait_all()
    assert len((await client.get(path + "/messages")).json()["items"]) == 1


async def test_keyless_nim_and_explicit_auto_preference(test_settings):
    from pydantic import SecretStr

    settings = test_settings.model_copy(
        update={
            "offline_mode": False,
            "harness_mode": "nim",
            "nim_base_url": "https://synthetic.invalid/v1",
            "nim_model": "SYNTHETIC",
            "nim_api_key": None,
            "anthropic_api_key": SecretStr("SYNTHETIC"),
        }
    )
    assert await select_provider("NIM", settings) == "NIM"
    assert await select_provider("AUTO", settings) == "NIM"


async def test_owner_revocation_blocks_assistant_persistence(client, actor_login, app, monkeypatch):
    import asyncio
    from uuid import UUID

    from sqlalchemy import select

    from darknetra.auth.models import User
    from darknetra.chats import providers, service
    from darknetra.chats.models import PrivateMessage

    user = await actor_login()
    started, release = asyncio.Event(), asyncio.Event()

    async def selected(*args):
        return "OFFLINE"

    async def generated(*args):
        started.set()
        await release.wait()
        yield {"type": "assistant", "text": "SYNTHETIC unauthorized late answer"}

    monkeypatch.setattr(providers, "select_provider", selected)
    monkeypatch.setattr(providers, "generate", generated)
    chat = (await client.post("/api/v1/chats", json={"title": "SYNTHETIC revocation"})).json()["id"]
    run = (
        await client.post(f"/api/v1/chats/{chat}/messages", json={"content": "SYNTHETIC request"})
    ).json()["run_id"]
    await asyncio.wait_for(started.wait(), 5)
    async with app.state.session_factory() as db:
        row = await db.get(User, user.id)
        row.is_active = False
        await db.commit()
    release.set()
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        row = await service.get_run(db, user.id, UUID(chat), UUID(run))
        assert row.status == "ERROR" and row.error["code"] == "FORBIDDEN"
        messages = list(
            (
                await db.scalars(
                    select(PrivateMessage).where(
                        PrivateMessage.owner_user_id == user.id,
                        PrivateMessage.thread_id == UUID(chat),
                    )
                )
            ).all()
        )
        assert len(messages) == 1
