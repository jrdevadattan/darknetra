"""Ordinary observation APIs cannot revive or expose unavailable source evidence."""

from uuid import UUID

import pytest
from sqlalchemy import select

from darknetra.errors import Conflict
from darknetra.evidence.models import Evidence
from darknetra.evidence.service import process_evidence


@pytest.mark.parametrize("status", ["FAILED", "EXPIRED", "QUARANTINED"])
async def test_unavailable_source_hides_entity_observation_and_search(
    client, actor_login, app, status
):
    actor = await actor_login()
    case = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC visibility", "demo": True})
    ).json()
    root = f"/api/v1/cases/{case['id']}"
    response = await client.post(
        root + "/evidence",
        files={
            "files": (
                "SYNTHETIC.html",
                b"<!doctype html><html><body><pre>SYNTHETIC\nVendor alias: SYNTHETIC_VISIBILITY_ALIAS\nSYNTHETIC withheld passage</pre></body></html>",
            )
        },
        data={"source_class": "SYNTHETIC"},
    )
    evidence = response.json()["results"][0]["evidence"]
    await app.state.jobs.wait_all()
    entity = (await client.get(root + "/entities")).json()["items"][0]
    before = await client.get(root + "/entities/" + entity["id"])
    observation_id = before.json()["observations"][0]["id"]
    async with app.state.session_factory() as db:
        source = await db.scalar(
            select(Evidence).where(
                Evidence.case_id == UUID(case["id"]), Evidence.id == UUID(evidence["id"])
            )
        )
        source.status = status
        await db.commit()
    assert not (await client.post(root + "/search", json={"query": "withheld"})).json()["hits"]
    assert not (await client.get(root + "/entities")).json()["items"]
    assert (await client.get(root + "/entities/" + entity["id"])).status_code == 404
    assert (await client.get(root + "/observations/" + observation_id)).status_code == 404
    if status == "EXPIRED":
        assert (
            await client.post(root + "/evidence/" + evidence["id"] + "/reprocess")
        ).status_code == 409
        async with app.state.session_factory() as db:
            source = await db.scalar(
                select(Evidence).where(
                    Evidence.case_id == UUID(case["id"]), Evidence.id == UUID(evidence["id"])
                )
            )
            with pytest.raises(Conflict):
                await process_evidence(db, source, actor, app.state.settings)
            assert source.status == "EXPIRED"
