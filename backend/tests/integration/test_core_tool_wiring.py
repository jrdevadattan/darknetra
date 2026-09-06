"""Registered tools exercise the same real case services as the public API."""

from datetime import UTC, datetime, timedelta

import base58

from darknetra.tools.invoke import invoke
from darknetra.tools.registry import REGISTRY


async def test_local_analytics_monitor_and_report_tools(client, actor_login, app):
    names = {
        "correlate_entities",
        "graph",
        "assess_wallet",
        "detect_trends",
        "list_alerts",
        "changes_since",
        "build_investigation_pack",
    }
    assert names <= REGISTRY.keys()
    assert "record_decision" not in REGISTRY
    await actor_login()
    response = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC tool services", "demo": True}
    )
    case_id = response.json()["id"]
    wallet = base58.b58encode_check(bytes([111]) + bytes(range(20))).decode()
    response = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={
            "files": ("SYNTHETIC.txt", f"SYNTHETIC wallet {wallet} maal 2 gm INR 2500".encode())
        },
        data={"source_class": "SYNTHETIC"},
    )
    evidence = response.json()["results"][0]["evidence"]
    await app.state.jobs.wait_all()
    results = {}
    arguments = {
        "correlate_entities": {},
        "graph": {"include_evidence": True},
        "assess_wallet": {"address": wallet, "live": False},
        "detect_trends": {"window_days": 7},
        "list_alerts": {},
        "changes_since": {"since": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        "build_investigation_pack": {"narrative": False},
    }

    class ToolsHarness:
        async def run(self, ctx, prompt, **kwargs):
            for name, args in arguments.items():
                results[name] = await invoke(ctx, name, args)
            yield {"type": "assistant", "text": "Insufficient evidence."}

    app.state.harness_factory = lambda _: ToolsHarness()
    response = await client.post(
        f"/api/v1/cases/{case_id}/threads", json={"title": "SYNTHETIC tools"}
    )
    thread_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/cases/{case_id}/threads/{thread_id}/messages",
        json={"content": "SYNTHETIC local tools"},
    )
    assert response.status_code == 202, response.text
    await app.state.jobs.wait_all()
    assert set(results) == names
    assert all(result.ok for result in results.values()), {
        name: result.error for name, result in results.items() if not result.ok
    }
    assert evidence["id"] in {str(identifier) for identifier in results["graph"].evidence_ids}
    assert results["assess_wallet"].data["assessment"]["gnn"] is None
    assert results["assess_wallet"].data["assessment"]["gnn_unavailable_reason"]
    assert results["build_investigation_pack"].data["status"] == "DONE"
    assert results["build_investigation_pack"].evidence_ids
