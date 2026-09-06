import asyncio

from sqlalchemy import select

from darknetra.extract.models import Observation


async def make_case(client):
    response = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC evidence isolation", "demo": True}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def upload(client, case, data=b"SYNTHETIC maal chitta 2 gm INR 2500", filename="sample.txt"):
    response = await client.post(
        f"/api/v1/cases/{case}/evidence",
        files={"files": (filename, data)},
        data={"source_class": "SYNTHETIC"},
    )
    assert response.status_code == 201, response.text
    assert not response.json()["errors"], response.text
    return response.json()["results"][0]


async def test_evidence_dedupe_spans_and_isolation(client, actor_login, app):
    await actor_login()
    case_a, case_b = await make_case(client), await make_case(client)
    first = await upload(client, case_a)
    duplicate = await upload(client, case_a)
    other = await upload(client, case_b)
    await app.state.jobs.wait_all()
    assert duplicate["duplicate"] and duplicate["evidence"]["id"] == first["evidence"]["id"]
    response = await client.post(
        f"/api/v1/cases/{case_a}/search", json={"query": "maal", "mode": "semantic"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["hits"] and result["mode_used"] == "lexical" and result["dense_available"] is False
    )
    assert all(hit["evidence"]["id"] != other["evidence"]["id"] for hit in result["hits"])
    assert (
        await client.get(f"/api/v1/cases/{case_a}/evidence/{other['evidence']['id']}")
    ).status_code == 404
    async with app.state.session_factory() as db:
        from uuid import UUID

        from darknetra.evidence.service import get_text

        text, _ = await get_text(
            db, UUID(case_a), UUID(first["evidence"]["id"]), app.state.settings
        )
        rows = list(
            await db.scalars(select(Observation).where(Observation.case_id == UUID(case_a)))
        )
        assert rows
        assert all(text[row.span_start : row.span_end] == row.raw for row in rows)
    context = await client.get(
        f"/api/v1/cases/{case_a}/evidence/{first['evidence']['code']}/context",
        params={"start": 0, "end": 9},
    )
    assert context.json()["text"] == "SYNTHETIC"


async def test_quarantine_reprocess_and_unique_codes(client, actor_login, app):
    await actor_login()
    case = await make_case(client)
    quarantined = await upload(client, case, b"SYNTHETIC script", "sample.ps1")
    eid = quarantined["evidence"]["id"]
    assert quarantined["evidence"]["status"] == "QUARANTINED"
    assert (
        await client.post(
            f"/api/v1/cases/{case}/evidence/{eid}/release", json={"rationale": "test"}
        )
    ).status_code == 409
    first, second = await asyncio.gather(
        upload(client, case, b"SYNTHETIC first"), upload(client, case, b"SYNTHETIC second")
    )
    await app.state.jobs.wait_all()
    assert first["evidence"]["code"] != second["evidence"]["code"]
    eid = first["evidence"]["id"]
    response = await client.post(f"/api/v1/cases/{case}/evidence/{eid}/reprocess")
    assert response.status_code == 200, response.text
    assert sorted(d["version"] for d in response.json()["derivatives"] if d["kind"] == "TEXT") == [
        1,
        2,
    ]
