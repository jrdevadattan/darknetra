"""M2: admin lexicon changes create new extraction versions, preserving old facts."""

from uuid import UUID, uuid4

from sqlalchemy import select

from darknetra.extract.models import ExtractionRun, Observation


async def test_taxonomy_permissions_variants_and_reextraction(client, actor_login, app):
    await actor_login()
    token = uuid4().hex[:12]
    canonical = "SYNTHETIC_TAXONOMY_" + token
    variant = "SYNTHETIC_ਫੁੱਲ_" + token
    body = {
        "canonical": canonical,
        "type": "SLANG",
        "variants": [{"term": variant, "language": "pa", "script": "Guru"}],
    }
    assert (await client.get("/api/v1/admin/taxonomy")).status_code == 403
    assert (await client.post("/api/v1/admin/taxonomy", json=body)).status_code == 403
    await actor_login("ADMIN")
    case = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC taxonomy", "demo": True})
    ).json()
    path = f"/api/v1/cases/{case['id']}"
    uploaded = await client.post(
        path + "/evidence",
        files={"files": ("SYNTHETIC.txt", ("SYNTHETIC quote " + variant).encode())},
        data={"source_class": "SYNTHETIC"},
    )
    evidence_id = uploaded.json()["results"][0]["evidence"]["id"]
    await app.state.jobs.wait_all()
    before = (await client.get(path + "/extraction/runs")).json()["items"][0]
    created = await client.post("/api/v1/admin/taxonomy", json=body)
    assert created.status_code == 201, created.text
    term_id = created.json()["id"]
    assert created.json()["variants"] == [{**body["variants"][0], "note": None}]
    assert (await client.post("/api/v1/admin/taxonomy", json=body)).status_code == 409
    listing = (await client.get("/api/v1/admin/taxonomy", params={"q": canonical})).json()
    assert [item["id"] for item in listing["items"]] == [term_id]
    extracted = await client.post(path + "/extraction/run", json={"evidence_id": evidence_id})
    assert extracted.status_code == 200, extracted.text
    run = extracted.json()[0]
    assert run["id"] != before["id"] and run["bundle_version"] != before["bundle_version"]
    async with app.state.session_factory() as db:
        observations = list(
            await db.scalars(
                select(Observation).where(
                    Observation.case_id == UUID(case["id"]),
                    Observation.run_id == UUID(run["id"]),
                    Observation.validator == "lexicon_exact",
                )
            )
        )
        matched = [row for row in observations if row.normalized["value"] == canonical]
        assert len(matched) == 1 and matched[0].raw == variant
        assert matched[0].meta["term_id"] == term_id
        assert matched[0].meta["language"] == "pa"
        observation_id = matched[0].id
    changed = await client.patch(f"/api/v1/admin/taxonomy/{term_id}", json={"active": False})
    assert changed.status_code == 200 and changed.json()["active"] is False
    latest = (
        await client.post(path + "/extraction/run", json={"evidence_id": evidence_id})
    ).json()[0]
    assert latest["bundle_version"] != run["bundle_version"]
    assert latest["id"] not in {before["id"], run["id"]}
    assert not (await client.get(path + "/entities", params={"q": canonical})).json()["items"]
    assert (await client.get(path + "/observations/" + str(observation_id))).status_code == 404
    async with app.state.session_factory() as db:
        previous = await db.scalar(
            select(Observation).where(
                Observation.case_id == UUID(case["id"]), Observation.id == observation_id
            )
        )
        assert previous.raw == variant and previous.normalized["value"] == canonical
        assert not list(
            await db.scalars(
                select(Observation).where(
                    Observation.case_id == UUID(case["id"]),
                    Observation.run_id == UUID(latest["id"]),
                    Observation.validator == "lexicon_exact",
                )
            )
        )
        assert await db.scalar(
            select(ExtractionRun.id).where(
                ExtractionRun.case_id == UUID(case["id"]), ExtractionRun.id == UUID(run["id"])
            )
        )
    await actor_login()
    assert (
        await client.patch(f"/api/v1/admin/taxonomy/{term_id}", json={"active": True})
    ).status_code == 403


async def test_taxonomy_replacement_preserves_group_id_and_bounds(client, actor_login):
    await actor_login("ADMIN")
    body = {
        "canonical": "SYNTHETIC_" + uuid4().hex,
        "type": "SLANG",
        "variants": [
            {"term": "SYNTHETIC old", "language": "en", "script": "Latn"},
            {"term": "SYNTHETIC other", "language": "en", "script": "Latn"},
        ],
    }
    created = await client.post("/api/v1/admin/taxonomy", json=body)
    assert created.status_code == 201, created.text
    term_id = created.json()["id"]
    variants = [{"term": "SYNTHETIC replacement", "language": "en", "script": "Latn"}]
    changed = await client.patch(f"/api/v1/admin/taxonomy/{term_id}", json={"variants": variants})
    assert changed.status_code == 200 and changed.json()["id"] == term_id
    assert (
        len(changed.json()["variants"]) == 1
        and changed.json()["variants"][0]["term"] == variants[0]["term"]
    )
    assert (
        await client.patch(f"/api/v1/admin/taxonomy/{term_id}", json={"variants": []})
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/admin/taxonomy", json={**body, "canonical": " ", "variants": variants}
        )
    ).status_code == 422
