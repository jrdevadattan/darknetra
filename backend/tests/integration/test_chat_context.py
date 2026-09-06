"""Scenario 18/27: attachments, pinned findings and contextual replay stay case-bound."""

import json
from uuid import UUID, uuid4

from darknetra.decisions.models import Finding


async def test_run_receives_attachment_and_pinned_finding_context(client, app, actor_login):
    user = await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC chat context"})).json()
    prefix = f"/api/v1/cases/{case['id']}"
    upload = await client.post(
        prefix + "/evidence",
        files={"files": ("SYNTHETIC.txt", b"SYNTHETIC blue parcel")},
        data={"source_class": "SYNTHETIC"},
    )
    evidence = upload.json()["results"][0]["evidence"]
    await app.state.jobs.wait_all()
    thread = (await client.post(prefix + "/threads", json={"title": "SYNTHETIC context"})).json()
    async with app.state.session_factory() as db:
        finding = Finding(
            id=uuid4(),
            case_id=UUID(case["id"]),
            title="SYNTHETIC pinned draft",
            claim="SYNTHETIC blue parcel",
            kind="CANDIDATE",
            status="DRAFT",
            evidence_ids=[UUID(evidence["id"])],
            method="SYNTHETIC fixture",
            created_by=user.id,
        )
        db.add(finding)
        await db.commit()
    thread_path = prefix + f"/threads/{thread['id']}"
    assert (
        await client.post(
            thread_path + "/pin", json={"finding_id": str(finding.id), "pinned": True}
        )
    ).status_code == 204
    calls = []

    class InspectHarness:
        async def run(self, ctx, prompt, **kwargs):
            calls.append(
                {
                    "prompt": prompt,
                    "history": kwargs["history"],
                    "codes": getattr(ctx, "context_evidence_codes", []),
                }
            )
            yield {"type": "assistant", "text": "Insufficient evidence."}

    app.state.harness_factory = lambda _: InspectHarness()
    for _ in range(2):
        response = await client.post(
            thread_path + "/messages",
            json={"content": "What does this show?", "attachments": [evidence["code"]]},
        )
        assert response.status_code == 202, response.text
        await app.state.jobs.wait_all()
    assert len(calls) == 2, "Different conversation histories must not share a replay entry"
    context = json.dumps(calls[0]["history"])
    assert evidence["code"] in context and str(finding.id) in context
    assert "CANDIDATE" in context and "DRAFT" in context
    assert calls[0]["codes"] == [evidence["code"]]
    assert any(item["content"] == "What does this show?" for item in calls[1]["history"])
    other = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC other"})).json()
    other_thread = (
        await client.post(
            f"/api/v1/cases/{other['id']}/threads", json={"title": "SYNTHETIC isolated"}
        )
    ).json()
    denied = await client.post(
        f"/api/v1/cases/{other['id']}/threads/{other_thread['id']}/messages",
        json={"content": "Read attached", "attachments": [evidence["code"]]},
    )
    assert denied.status_code == 404


async def test_deterministic_chat_reads_the_attached_evidence(client, app, actor_login):
    await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC attachment read"})).json()
    prefix = f"/api/v1/cases/{case['id']}"
    upload = await client.post(
        prefix + "/evidence",
        files={"files": ("SYNTHETIC.txt", b"SYNTHETIC blue parcel")},
        data={"source_class": "SYNTHETIC"},
    )
    evidence = upload.json()["results"][0]["evidence"]
    await app.state.jobs.wait_all()
    thread = (await client.post(prefix + "/threads", json={"title": "SYNTHETIC read"})).json()
    path = prefix + f"/threads/{thread['id']}"
    response = await client.post(
        path + "/messages",
        json={"content": "Read this attachment", "attachments": [evidence["code"]]},
    )
    assert response.status_code == 202, response.text
    await app.state.jobs.wait_all()
    messages = (await client.get(path + "/messages")).json()["items"]
    answer = next(message for message in messages if message["role"] == "ASSISTANT")
    assert answer["verification"]["ok"]
    assert any(evidence["code"] in claim["evidence_codes"] for claim in answer["claims"])
