"""M2 provenance: exact source spans attribute signals only to their publisher."""

import json
from uuid import UUID

from sqlalchemy import select

from darknetra.cases.models import CaseMembership
from darknetra.evidence.models import Evidence
from darknetra.evidence.service import get_text
from darknetra.extract.models import Observation


async def test_message_ownership_and_synthetic_family(client, actor_login, app):
    await actor_login()
    case_response = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC attribution", "demo": True}
    )
    case_response.raise_for_status()
    case_id = case_response.json()["id"]
    rows = [
        {
            "id": 1,
            "type": "message",
            "date": "2026-09-01T10:00:00",
            "from": "SYNTHETIC_SENDER_A",
            "text": "SYNTHETIC wickr:synthetic_contact_a\ncontinued",
        },
        {
            "id": 2,
            "type": "message",
            "date": "2026-09-01T10:01:00",
            "from": "SYNTHETIC_SENDER_B",
            "text": "SYNTHETIC wickr:synthetic_contact_b",
        },
    ]
    uploaded = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"files": ("SYNTHETIC.json", json.dumps({"messages": rows}).encode())},
        data={"source_class": "SYNTHETIC", "source_family": "SYNTHETIC_CHAT_A"},
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence = uploaded.json()["results"][0]["evidence"]
    await app.state.jobs.wait_all()
    detail = await client.get(f"/api/v1/cases/{case_id}/evidence/{evidence['id']}")
    assert detail.json()["meta"]["source_family"] == "SYNTHETIC_CHAT_A"
    async with app.state.session_factory() as db:
        text, _ = await get_text(db, UUID(case_id), UUID(evidence["id"]), app.state.settings)
        observations = list(
            await db.scalars(select(Observation).where(Observation.case_id == UUID(case_id)))
        )
        senders = {o.normalized["value"]: o for o in observations if o.type == "VENDOR_ALIAS"}
        assert set(senders) == {"synthetic_sender_a", "synthetic_sender_b"}
        contacts = [o for o in observations if o.type == "CONTACT_HANDLE"]
        assert len(contacts) == 2
        for contact in contacts:
            sender = senders[contact.meta["subject_value"]]
            context = sender.meta["context_span"]
            assert context["start"] <= contact.span_start < contact.span_end <= context["end"]
            assert text[contact.span_start : contact.span_end] == contact.raw
            assert text[sender.span_start : sender.span_end] == sender.raw
            assert sender.meta["role"] == "sender"
            assert sender.meta["timestamp"].startswith("2026-09-01")
            assert contact.meta["message_id"] == sender.meta["message_id"]


async def test_non_synthetic_upload_cannot_set_demo_source_family(client, actor_login):
    await actor_login()
    response = await client.post("/api/v1/cases", json={"title": "SYNTHETIC regular case"})
    case_id = response.json()["id"]
    response = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"files": ("SYNTHETIC.txt", b"SYNTHETIC")},
        data={"source_class": "UPLOAD", "source_family": "SYNTHETIC_CHAT_A"},
    )
    assert response.status_code == 422


async def test_authorized_quarantine_search_is_explicit_and_role_gated(client, actor_login, app):
    actor = await actor_login()
    response = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC quarantine search", "demo": True}
    )
    case_id = UUID(response.json()["id"])
    response = await client.post(
        f"/api/v1/cases/{case_id}/evidence",
        files={"files": ("SYNTHETIC.txt", b"SYNTHETIC withheld passage")},
        data={"source_class": "SYNTHETIC"},
    )
    evidence_id = UUID(response.json()["results"][0]["evidence"]["id"])
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        row = await db.scalar(
            select(Evidence).where(Evidence.case_id == case_id, Evidence.id == evidence_id)
        )
        row.status = "QUARANTINED"
        await db.commit()
    query = {"query": "withheld", "filters": {"include_quarantined": True}}
    response = await client.post(f"/api/v1/cases/{case_id}/search", json=query)
    assert response.status_code == 200 and response.json()["hits"], response.text
    assert not (
        await client.post(f"/api/v1/cases/{case_id}/search", json={"query": "withheld"})
    ).json()["hits"]
    async with app.state.session_factory() as db:
        member = await db.scalar(
            select(CaseMembership).where(
                CaseMembership.case_id == case_id, CaseMembership.user_id == actor.id
            )
        )
        member.role = "VIEWER"
        await db.commit()
    assert (await client.post(f"/api/v1/cases/{case_id}/search", json=query)).status_code == 403
