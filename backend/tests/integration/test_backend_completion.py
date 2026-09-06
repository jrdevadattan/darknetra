from uuid import UUID

import pytest
from sqlalchemy import select

from darknetra.auth.models import User
from darknetra.monitor.models import Alert, MonitorRun, WatchlistItem
from darknetra.monitor.scheduler import MonitorScheduler


async def make_watch(client):
    case = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC completion", "demo": True})
    ).json()
    base = "/api/v1/cases/" + case["id"]
    watch = (await client.post(base + "/watchlists", json={"name": "SYNTHETIC watch"})).json()
    item = (
        await client.post(
            base + "/watchlists/" + watch["id"] + "/items",
            json={"type": "KEYWORD", "value": "SYNTHETIC", "sources": ["evidence"]},
        )
    ).json()
    return UUID(case["id"]), UUID(item["id"])


async def test_revoked_monitor_principal_has_persisted_error_and_alert(client, app, actor_login):
    user = await actor_login()
    cid, iid = await make_watch(client)
    async with app.state.session_factory() as db:
        row = await db.get(User, user.id)
        row.is_active = False
        await db.commit()
    scheduler = MonitorScheduler(app, None)
    await scheduler.run_now(cid, iid)
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        run = await db.scalar(
            select(MonitorRun).where(MonitorRun.case_id == cid, MonitorRun.item_id == iid)
        )
        assert (
            run.status == "ERROR" and run.errors["execution_principal"]["code"] == "POLICY_DENIED"
        )
        item = await db.scalar(
            select(WatchlistItem).where(WatchlistItem.case_id == cid, WatchlistItem.id == iid)
        )
        assert item.state["suspension_reason"]
        assert await db.scalar(
            select(Alert.id).where(Alert.case_id == cid, Alert.kind == "MONITOR_ERROR")
        )


async def test_plugins_require_admin_and_block_cached_invocation(client, app, actor_login):
    from sqlalchemy import delete

    from darknetra.audit.service import digest
    from darknetra.auth.service import user_actor
    from darknetra.settings.models import Setting
    from darknetra.tools.contracts import ToolContext, ToolResult
    from darknetra.tools.invoke import invoke

    user = await actor_login()
    cid, _ = await make_watch(client)
    plugin = next(
        p for p in (await client.get("/api/v1/plugins")).json()["items"] if p["id"] == "robin"
    )
    patch = {"enabled": False, "manifest_hash": plugin["manifest_hash"]}
    async with app.state.session_factory() as db:
        prior = await db.get(Setting, "plugin:robin")
        previous = prior.value if prior else None
    assert (await client.patch("/api/v1/admin/plugins/robin", json=patch)).status_code == 403
    await actor_login("ADMIN")
    assert (await client.patch("/api/v1/admin/plugins/robin", json=patch)).status_code == 200
    try:
        ctx = ToolContext(
            case_id=cid,
            actor=user_actor(user),
            settings=app.state.settings,
            session_factory=app.state.session_factory,
        )
        args = {"query": "SYNTHETIC"}
        ctx.cache["robin_search:" + digest(args)] = ToolResult(ok=True, data={"cached": True})
        result = await invoke(ctx, "robin_search", args)
        assert result.error["code"] == "POLICY_DENIED"
        assert "Plugin disabled" in result.error["message"]
    finally:
        assert (
            await client.patch("/api/v1/admin/plugins/robin", json={**patch, "enabled": True})
        ).status_code == 200
        async with app.state.session_factory() as db:
            row = await db.get(Setting, "plugin:robin")
            if previous is None:
                await db.execute(delete(Setting).where(Setting.key == "plugin:robin"))
            else:
                row.value = previous
            await db.commit()


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"prompt_tokens": -1, "completion_tokens": 2},
        {"prompt_tokens": "10", "completion_tokens": 2},
    ],
)
def test_nim_invalid_usage_is_never_complete(usage):
    from types import SimpleNamespace

    from darknetra.agent.harness_nim import _usage_event

    ctx = SimpleNamespace(
        settings=SimpleNamespace(nim_input_cost_per_million=1, nim_output_cost_per_million=1)
    )
    assert _usage_event(ctx, usage)["cost_complete"] is False


async def test_digest_and_six_message_memory(client, app, actor_login):
    await actor_login()
    cid, _ = await make_watch(client)
    base = "/api/v1/cases/" + str(cid)
    thread = (await client.post(base + "/threads", json={"title": "SYNTHETIC memory"})).json()
    for index in range(6):
        response = await client.post(
            base + "/threads/" + thread["id"] + "/messages",
            json={"content": f"SYNTHETIC request {index}"},
        )
        assert response.status_code == 202
        await app.state.jobs.wait_all()
    detail = (await client.get(base + "/threads/" + thread["id"])).json()
    assert "SYNTHETIC request 0" in detail["summary"]
    digest = await client.get(base + "/digest")
    assert digest.status_code == 200 and digest.json()["case_id"] == str(cid)
    assert len(digest.json()["top_alerts"]) <= 10
    assert (await client.get(base + "/digest?since=2026-01-01T00:00:00")).status_code == 422
    await actor_login()
    assert (await client.get(base + "/digest")).status_code == 404


async def test_digest_counts_current_pending_pairs_not_historical_versions(
    client, app, actor_login
):
    from darknetra.analytics.models import LinkCandidate
    from tests.integration.test_analytics_api import make_case, seed_pair

    await actor_login()
    cid, other = await make_case(client), await make_case(client)
    candidate_id, _, _ = await seed_pair(app, cid)
    await seed_pair(app, other)
    async with app.state.session_factory() as db:
        previous = await db.get(LinkCandidate, candidate_id)
        db.add(
            LinkCandidate(
                case_id=previous.case_id,
                run_id=previous.run_id,
                subject_a_id=previous.subject_a_id,
                subject_b_id=previous.subject_b_id,
                score=previous.score,
                band=previous.band,
                version=2,
                supersedes_id=previous.id,
                status="PENDING",
                feature_digest="2" * 64,
            )
        )
        await db.commit()
    digest = (await client.get(f"/api/v1/cases/{cid}/digest")).json()
    assert digest["pending_candidates"] == 1
    async with app.state.session_factory() as db:
        current = await db.scalar(
            select(LinkCandidate).where(
                LinkCandidate.case_id == UUID(cid), LinkCandidate.version == 2
            )
        )
        # Test fixture models an already reviewed latest version, leaving history pending.
        current.status = "REJECTED"
        await db.commit()
    assert (await client.get(f"/api/v1/cases/{cid}/digest")).json()["pending_candidates"] == 0


async def test_reader_lines_agree_with_stored_offsets_across_page_separator(
    client, app, actor_login
):
    from darknetra.auth.service import user_actor
    from darknetra.tools.contracts import ToolContext
    from darknetra.tools.invoke import invoke
    from tests.integration.test_monitor_reports_api import add_evidence

    user = await actor_login()
    cid, _ = await make_watch(client)
    evidence = await add_evidence(client, app, cid, content="SYNTHETIC first\n\f\nSYNTHETIC second")
    ctx = ToolContext(
        case_id=cid,
        actor=user_actor(user),
        settings=app.state.settings,
        session_factory=app.state.session_factory,
    )
    result = await invoke(
        ctx,
        "read_evidence",
        {
            "evidence_code": evidence["code"],
            "start_line": 3,
            "end_line": 3,
        },
    )
    assert result.ok and result.data["text"] == "SYNTHETIC second"
    assert result.data["start_line"] == result.data["end_line"] == 3
