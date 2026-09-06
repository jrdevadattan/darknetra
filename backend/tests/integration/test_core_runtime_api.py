"""Scenarios 18/19/24/27/42: real HTTP, PostgreSQL, and bounded synthetic sources."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import base58
import pgpy
from pgpy.constants import PubKeyAlgorithm
from sqlalchemy import select

from darknetra.audit.models import AuditEvent
from darknetra.capture.fetcher import Fetched, SafeHttp
from darknetra.evidence.models import Evidence
from darknetra.tools.invoke import invoke


async def create_case(client, title="SYNTHETIC runtime"):
    response = await client.post("/api/v1/cases", json={"title": title, "demo": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def upload(client, case_id, filename, data):
    response = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"files": (filename, data)},
        data={"source_class": "SYNTHETIC"},
    )
    assert response.status_code == 201 and not response.json()["errors"], response.text
    return response.json()["results"][0]["evidence"]


async def create_thread(client, case_id):
    response = await client.post(
        f"/api/v1/cases/{case_id}/threads", json={"title": "SYNTHETIC cited question"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def run_question(client, app, case_id, thread_id, question):
    prefix = f"/api/v1/cases/{case_id}/threads/{thread_id}"
    response = await client.post(prefix + "/messages", json={"content": question})
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    await app.state.jobs.wait_all()
    response = await client.get(prefix + f"/runs/{run_id}")
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "DONE", run
    events = await client.get(prefix + f"/runs/{run_id}/events")
    assert events.status_code == 200, events.text
    parsed = []
    for block in events.text.replace("\r\n", "\n").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "data" in fields:
            parsed.append(
                {
                    "id": int(fields["id"]),
                    "event": fields["event"],
                    "data": json.loads(fields["data"]),
                }
            )
    return prefix, run_id, run, parsed


async def test_wallet_key_answer_sse_replay_and_isolation(client, actor_login, app):
    await actor_login()
    case_id = await create_case(client)
    other_case = await create_case(client, "SYNTHETIC second case")
    wallet = base58.b58encode_check(bytes([111]) + bytes(range(20))).decode()
    first = await upload(
        client, case_id, "SYNTHETIC-wallet.txt", f"SYNTHETIC wallet {wallet}".encode()
    )
    key = pgpy.PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, 1024)
    second = await upload(
        client,
        case_id,
        "SYNTHETIC-public-key.asc",
        ("SYNTHETIC PUBLIC TEST KEY\n" + str(key.pubkey)).encode(),
    )
    await app.state.jobs.wait_all()
    thread_id = await create_thread(client, case_id)
    question = "What wallets and PGP keys are in this case?"
    prefix, original_id, run, events = await run_question(client, app, case_id, thread_id, question)
    assert [event["id"] for event in events] == list(range(1, len(events) + 1))
    assert events[0]["event"] == "run.started" and events[-1]["event"] == "run.finished"
    assert len([event for event in events if event["event"] == "run.step"]) >= 2
    messages = [
        event["data"]["message"] for event in events if event["event"] == "message.completed"
    ]
    assert messages and all(message["verification"]["ok"] for message in messages)
    codes = {
        code
        for message in messages
        for claim in message["claims"]
        if claim["verified"]
        for code in claim["evidence_codes"]
    }
    assert {first["code"], second["code"]} <= codes
    reconnect = await client.get(
        prefix + f"/runs/{original_id}/events", headers={"Last-Event-ID": str(events[-2]["id"])}
    )
    assert reconnect.text.count("event:") == 1 and "event: run.finished" in reconnect.text
    assert (
        await client.get(
            f"/api/v1/cases/{other_case}/threads/{thread_id}/runs/{original_id}/events"
        )
    ).status_code == 404
    replay_thread = await create_thread(client, case_id)
    _, _, replay, replay_events = await run_question(client, app, case_id, replay_thread, question)
    assert replay["replayed_from_run_id"] == original_id
    assert replay_events[0]["data"]["replayed"] is True
    await upload(client, case_id, "SYNTHETIC-new.txt", b"SYNTHETIC changed state")
    await app.state.jobs.wait_all()
    fresh_thread = await create_thread(client, case_id)
    _, _, fresh, _ = await run_question(client, app, case_id, fresh_thread, question)
    assert fresh["replayed_from_run_id"] is None


async def test_capture_persists_before_cited_answer_and_offline_denial(
    client, actor_login, app, monkeypatch
):
    await actor_login()
    case_id = await create_case(client)
    other_case = await create_case(client, "SYNTHETIC unrelated")
    app.state.settings.offline_mode = False
    body = b"<p>SYNTHETIC public research fixture</p>"

    async def fetch(self, url, method="GET"):
        return Fetched(
            body, "text/html", url, 200, {"content-type": "text/html"}, datetime.now(UTC)
        )

    monkeypatch.setattr(SafeHttp, "fetch", fetch)

    class CaptureHarness:
        async def run(self, ctx, prompt, **kwargs):
            result = await invoke(
                ctx,
                "fetch_page",
                {"url": "https://synthetic.example.invalid/page", "case_id": other_case},
            )
            if result.ok:
                yield {
                    "type": "assistant",
                    "text": f"{result.data['excerpt']} [{result.data['evidence_code']}]",
                }
            else:
                yield {"type": "assistant", "text": "Insufficient evidence."}

    app.state.harness_factory = lambda _: CaptureHarness()
    thread_id = await create_thread(client, case_id)
    _, _, run, events = await run_question(client, app, case_id, thread_id, "SYNTHETIC capture")
    assert run["tool_calls"][0]["status"] == "DONE"
    assert any(event["event"] == "store.changed" for event in events)
    assert any(
        event["event"] == "message.completed" and event["data"]["message"]["verification"]["ok"]
        for event in events
    )
    async with app.state.session_factory() as db:
        captured = list(
            await db.scalars(
                select(Evidence).where(
                    Evidence.case_id == UUID(case_id), Evidence.origin == "CAPTURE"
                )
            )
        )
        assert len(captured) == 1 and captured[0].sha256 == hashlib.sha256(body).hexdigest()
        assert not list(
            await db.scalars(select(Evidence).where(Evidence.case_id == UUID(other_case)))
        )
    app.state.settings.offline_mode = True
    _, _, denied, _ = await run_question(
        client, app, case_id, thread_id, "SYNTHETIC offline capture"
    )
    assert denied["tool_calls"][0]["error"]["code"] == "NETWORK_REQUIRED"
    async with app.state.session_factory() as db:
        events = list(
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.case_id == UUID(case_id), AuditEvent.action == "tool.call"
                )
            )
        )
        assert any(event.detail.get("error_code") == "NETWORK_REQUIRED" for event in events)


async def test_threads_paginate_without_duplicates(client, actor_login):
    await actor_login()
    case_id = await create_case(client)
    expected = {await create_thread(client, case_id) for _ in range(3)}
    seen = set()
    cursor = None
    for _ in range(3):
        response = await client.get(
            f"/api/v1/cases/{case_id}/threads",
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert len(page["items"]) == 1 and page["items"][0]["id"] not in seen
        seen.add(page["items"][0]["id"])
        cursor = page["next_cursor"]
    assert seen == expected and cursor is None


async def test_extract_all_uses_text_derivatives_and_returns_counts(client, actor_login, app):
    import io

    from PIL import Image

    await actor_login()
    case_id = await create_case(client)
    await upload(client, case_id, "SYNTHETIC.txt", b"SYNTHETIC maal 2 gm INR 2500")
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(image, "PNG")
    await upload(client, case_id, "SYNTHETIC.png", image.getvalue())
    await app.state.jobs.wait_all()
    results = []

    class ExtractHarness:
        async def run(self, ctx, prompt, **kwargs):
            results.append(await invoke(ctx, "extract_indicators", {"evidence_code": "all"}))
            yield {"type": "assistant", "text": "Insufficient evidence."}

    app.state.harness_factory = lambda _: ExtractHarness()
    thread_id = await create_thread(client, case_id)
    await run_question(client, app, case_id, thread_id, "SYNTHETIC extract stored documents")
    assert results[0].ok, results[0].error
    assert len(results[0].data["run_ids"]) == 1
    assert results[0].data["counts_by_type"]["PRICE"] == 1
