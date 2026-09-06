"""SYNTHETIC activity histories are durable, correlated and case-isolated."""

from uuid import uuid4

from darknetra.tools.invoke import invoke


class TwoCalls:
    async def run(self, ctx, prompt, **kwargs):
        await invoke(ctx, "search_evidence", {"query": "SYNTHETIC missing", "k": 2})
        await invoke(ctx, "search_evidence", {"query": "SYNTHETIC missing", "k": 2})
        yield {"type": "assistant", "text": "Insufficient evidence."}
        yield {"type": "usage", "cost_usd": 0}


async def test_snapshot_repeated_calls_cursor_and_case_boundary(client, actor_login, app):
    await actor_login()
    app.state.harness_factory = lambda mode: TwoCalls()
    case = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC activity", "demo": True})
    ).json()
    base = f"/api/v1/cases/{case['id']}"
    thread = (await client.post(base + "/threads", json={"title": "SYNTHETIC steps"})).json()
    base += f"/threads/{thread['id']}"
    response = await client.post(base + "/messages", json={"content": "SYNTHETIC read"})
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    await app.state.jobs.wait_all()
    run_base = base + f"/runs/{run_id}"
    response = await client.get(run_base + "/execution")
    assert response.status_code == 200, response.text
    graph = response.json()
    assert graph["run_status"] == "DONE"
    calls = [n for n in graph["nodes"] if n["kind"] == "tool"]
    assert len(calls) == 2 and calls[0]["id"] != calls[1]["id"]
    assert all(n["status"] == "completed" for n in calls)
    assert sum(n["cached"] for n in calls) == 1
    assert not graph["truncated"]
    assert graph["events"] and all(e["seq"] <= graph["cursor"] for e in graph["events"])
    persisted = (await client.get(run_base)).json()["tool_calls"]
    assert {c["id"] for c in persisted} == {n["id"] for n in calls}
    resumed = await client.get(
        run_base + "/events", headers={"Last-Event-ID": str(graph["cursor"])}
    )
    assert "event: activity.updated" not in resumed.text
    other = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC other"})).json()
    wrong = run_base.replace(case["id"], other["id"])
    assert (await client.get(wrong + "/execution")).status_code == 404
    assert (
        await client.get(run_base.replace(run_id, str(uuid4())) + "/execution")
    ).status_code == 404
    await actor_login()
    assert (await client.get(run_base + "/execution")).status_code == 404


async def test_catalog_discloses_adapter_not_invented_remote_server(client, actor_login):
    await actor_login()
    tools = (await client.get("/api/v1/tools")).json()["items"]
    robin = next(t for t in tools if t["name"] == "robin_search")
    assert robin["integration_id"] == "robin"
    assert robin["adapter_kind"] == "local_adapter"
    assert robin["server"] is None
    assert robin["input_schema"]["properties"]["query"]


async def test_delegated_graph_is_reconstructible_and_omits_private_worker_events(
    client, actor_login, app
):
    from darknetra.tools.contracts import AgentRole

    class DelegatingHarness:
        async def run(self, ctx, prompt, **kwargs):
            if ctx.role == AgentRole.CASE_LEAD:
                result = await invoke(
                    ctx, "delegate_task", {"role": "EVIDENCE_ANALYST", "task": "SYNTHETIC check"}
                )
                assert result.ok, result.error
            else:
                await invoke(ctx, "search_evidence", {"query": "SYNTHETIC missing", "k": 2})
                yield {"type": "thinking", "data": {"text": "SYNTHETIC_PRIVATE_REASONING"}}
            yield {"type": "assistant", "text": "Insufficient evidence."}
            yield {"type": "usage", "cost_usd": 0}

    await actor_login()
    app.state.harness_factory = lambda _: DelegatingHarness()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC child graph"})).json()
    base = f"/api/v1/cases/{case['id']}"
    thread = (await client.post(base + "/threads", json={"title": "SYNTHETIC graph"})).json()
    base += f"/threads/{thread['id']}"
    response = await client.post(base + "/messages", json={"content": "SYNTHETIC delegate"})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    await app.state.jobs.wait_all()
    graph_response = await client.get(base + f"/runs/{run_id}/execution")
    graph = graph_response.json()
    assert graph["run_status"] == "DONE"
    child = next(n for n in graph["nodes"] if n["kind"] == "agent" and n["id"] != run_id)
    delegate = next(n for n in graph["nodes"] if n["tool_name"] == "delegate_task")
    child_tool = next(n for n in graph["nodes"] if n["tool_name"] == "search_evidence")
    assert delegate["parent_id"] == run_id
    assert child["parent_id"] == delegate["id"]
    assert child_tool["parent_id"] == child["id"]
    assert all(n["status"] == "completed" for n in graph["nodes"])
    assert graph["cost_complete"] is True
    assert "SYNTHETIC_PRIVATE_REASONING" not in graph_response.text
