"""M4 API and database scenarios; all fixtures are SYNTHETIC."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select


async def make_case(client, title="SYNTHETIC analytics"):
    response = await client.post("/api/v1/cases", json={"title": title, "demo": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def seed_pair(app, case_id):
    from uuid import UUID

    from darknetra.analytics.models import AnalyticRun, LinkCandidate
    from darknetra.evidence.models import Evidence
    from darknetra.extract.models import CanonicalEntity

    case_id, now = UUID(case_id), datetime.now(UTC)
    async with app.state.session_factory() as db:
        entities = [
            CanonicalEntity(
                id=uuid4(),
                case_id=case_id,
                type="VENDOR_ALIAS",
                value=f"SYNTHETIC_{i}",
                display=f"SYNTHETIC_{i}",
                first_seen_at=now,
                last_seen_at=now,
                observation_count=1,
                attrs={},
            )
            for i in range(2)
        ]
        evidence = Evidence(
            id=uuid4(),
            case_id=case_id,
            code="E-0001",
            sha256=uuid4().hex * 2,
            size_bytes=30,
            mime="text/plain",
            kind="TEXT",
            original_filename="SYNTHETIC.txt",
            storage_key="synthetic-unused",
            source_class="SYNTHETIC",
            origin="UPLOAD",
            status="READY",
            captured_at=now,
            requested_by_kind="SYSTEM",
            created_by_kind="SYSTEM",
            warnings=[],
            meta={},
        )
        run = AnalyticRun(
            id=uuid4(),
            case_id=case_id,
            kind="CORRELATION",
            version="test-v1",
            config_digest="0" * 64,
            status="DONE",
            started_at=now,
            finished_at=now,
            stats={},
        )
        db.add_all([*entities, evidence, run])
        await db.flush()
        a, b = sorted(entities, key=lambda x: x.id)
        candidate = LinkCandidate(
            id=uuid4(),
            case_id=case_id,
            run_id=run.id,
            subject_a_id=a.id,
            subject_b_id=b.id,
            score=40,
            band="POSSIBLE",
            features=[],
            evidence_ids=[evidence.id],
            contradictions=[],
            families=[],
            status="PENDING",
            version=1,
            feature_digest="1" * 64,
            meta={},
        )
        db.add(candidate)
        await db.commit()
        return candidate.id, evidence.id, (a.id, b.id)


@pytest.mark.integration
async def test_analytics_empty_panels_are_available(client, actor_login):
    await actor_login()
    case = await make_case(client)
    for path in (
        "analytics/links",
        "analytics/activity",
        "graph",
        "wallets",
        "trends",
        "decisions",
        "findings",
    ):
        response = await client.get(f"/api/v1/cases/{case}/{path}")
        assert response.status_code == 200, (path, response.text)


@pytest.mark.integration
async def test_scenario_17_decision_conflict_supersession_and_graph(app, client, actor_login):
    from darknetra.decisions.models import Decision

    await actor_login()
    case = await make_case(client)
    candidate, _, _ = await seed_pair(app, case)
    body = {
        "target_type": "LINK",
        "target_id": str(candidate),
        "decision": "ACCEPT",
        "rationale": "SYNTHETIC analyst reviewed supporting evidence",
    }
    first = await client.post(f"/api/v1/cases/{case}/decisions", json=body)
    assert first.status_code == 201, first.text
    conflict = await client.post(f"/api/v1/cases/{case}/decisions", json=body)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["detail"]["existing_decision"]["id"] == first.json()["id"]
    graph = (await client.get(f"/api/v1/cases/{case}/graph")).json()
    assert any(
        e["type"] == "ANALYST_CONFIRMED_RELATED" and e["status"] == "CONFIRMED"
        for e in graph["edges"]
    )
    body.update(
        decision="REJECT", supersede=True, rationale="SYNTHETIC review found contradictory evidence"
    )
    replacement = await client.post(f"/api/v1/cases/{case}/decisions", json=body)
    assert replacement.status_code == 201, replacement.text
    decisions = (await client.get(f"/api/v1/cases/{case}/decisions")).json()["items"]
    original = next(x for x in decisions if x["id"] == first.json()["id"])
    assert original["decision"] == "ACCEPT"
    assert original["superseded_by"] == replacement.json()["id"]
    graph = (await client.get(f"/api/v1/cases/{case}/graph")).json()
    assert not any(e["type"] == "ANALYST_CONFIRMED_RELATED" for e in graph["edges"])
    async with app.state.session_factory() as db:
        rows = list(await db.scalars(select(Decision).where(Decision.case_id == case)))
        assert len(rows) == 2
        assert next(r for r in rows if str(r.id) == first.json()["id"]).supersedes_id is None


@pytest.mark.integration
async def test_findings_require_same_case_evidence_and_matching_human_decision(
    app, client, actor_login
):
    await actor_login()
    case = await make_case(client)
    other = await make_case(client, "SYNTHETIC other")
    _, _, _ = await seed_pair(app, case)
    data = {
        "title": "SYNTHETIC observation",
        "claim": "SYNTHETIC fixture contains the reviewed alias",
        "evidence_codes": ["E-0001"],
        "method": "analyst review",
        "kind_hint": "CONFIRMED",
    }
    forged = await client.post(f"/api/v1/cases/{case}/findings", json=data)
    assert forged.status_code == 422, forged.text
    data["kind_hint"] = "OBSERVED"
    missing = await client.post(f"/api/v1/cases/{other}/findings", json=data)
    assert missing.status_code == 404, missing.text
    created = await client.post(f"/api/v1/cases/{case}/findings", json=data)
    assert created.status_code == 201, created.text
    finding = created.json()
    assert finding["kind"] == "OBSERVED" and finding["status"] == "DRAFT"
    decision = await client.post(
        f"/api/v1/cases/{case}/decisions",
        json={
            "target_type": "FINDING",
            "target_id": finding["id"],
            "decision": "ACCEPT",
            "rationale": "SYNTHETIC analyst checked the cited source",
        },
    )
    assert decision.status_code == 201, decision.text
    promoted = await client.post(
        f"/api/v1/cases/{case}/findings/{finding['id']}/promote",
        json={"decision_id": decision.json()["id"]},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["kind"] == "CONFIRMED"
    assert promoted.json()["status"] == "PROMOTED"
    leak = await client.get(f"/api/v1/cases/{other}/analytics/links/{uuid4()}")
    assert leak.status_code == 404


@pytest.mark.integration
async def test_ledger_import_is_bounded_case_scoped_and_idempotent(client, actor_login):
    import base58

    await actor_login()
    case = await make_case(client)
    address = base58.b58encode_check(bytes([111]) + bytes([42]) * 20).decode()
    nodes = (
        "source_class,node_index,timestep,label," + ",".join(f"f_{i}" for i in range(102)) + "\n"
    )
    nodes += "SYNTHETIC,0,1,2," + ",".join("0.1" for _ in range(102)) + "\n"
    files = {
        "nodes": ("nodes.csv", nodes),
        "edges": ("edges.csv", "source_class,src,dst\n"),
        "address_map": (
            "address_map.csv",
            f"source_class,address,chain,node_index,tag\nSYNTHETIC,{address},BTC,0,shared_service\n",
        ),
    }
    response = await client.post(f"/api/v1/cases/{case}/ledger/import", files=files)
    assert response.status_code == 200, response.text
    assert response.json() == {"nodes": 1, "edges": 0, "addresses": 1}
    duplicate = await client.post(f"/api/v1/cases/{case}/ledger/import", files=files)
    assert duplicate.status_code == 200, duplicate.text
    assessment = await client.post(
        f"/api/v1/cases/{case}/wallets/assess", json={"address": address}
    )
    assert assessment.status_code == 200, assessment.text
    result = assessment.json()
    assert result["gnn"] is None and result["gnn_unavailable_reason"]
    assert result["sanctions"] is None
    assert result["live_summary"]["sanctions_unavailable_reason"]
    assert result["tags"] == ["shared_service"]
    live = await client.post(
        f"/api/v1/cases/{case}/wallets/assess", json={"address": address, "live": True}
    )
    assert live.status_code == 503 and live.json()["error"]["code"] == "NETWORK_REQUIRED"


async def upload_text(client, case, text, name="SYNTHETIC.txt"):
    if name.endswith(".html"):
        import html

        text = "<!doctype html><html><body><pre>" + html.escape(text) + "</pre></body></html>"
    response = await client.post(
        f"/api/v1/cases/{case}/evidence",
        files={"files": (name, text)},
        data={"source_class": "SYNTHETIC"},
    )
    assert response.status_code == 201, response.text
    assert not response.json()["errors"], response.text
    return response.json()["results"][0]["evidence"]


@pytest.mark.integration
async def test_scenario_16_correlation_rescores_without_reusing_confirmation(
    app, client, actor_login
):
    await actor_login()
    case = await make_case(client)
    for alias in ("SYNTHETIC_NORTH", "SYNTHETIC_SOUTH"):
        await upload_text(
            client,
            case,
            f"Vendor alias: {alias}\nSYNTHETIC training\nContact wickr:synthetic_shared\nchitta 2 gm INR 2500",
            f"{alias}.html",
        )
    await app.state.jobs.wait_all()
    first = await client.post(f"/api/v1/cases/{case}/analytics/correlate", json={})
    assert first.status_code == 200, first.text
    links = (await client.get(f"/api/v1/cases/{case}/analytics/links")).json()["items"]
    assert len(links) == 1, links
    original = links[0]
    assert original["version"] == 1
    feature = next(f for f in original["features"] if f["name"] == "contact_reuse")
    assert len(feature["evidence"]) == 2 and feature["contribution"] == 15
    decision = await client.post(
        f"/api/v1/cases/{case}/decisions",
        json={
            "target_type": "LINK",
            "target_id": original["id"],
            "decision": "ACCEPT",
            "rationale": "SYNTHETIC analyst accepts only this evidence version",
        },
    )
    assert decision.status_code == 201, decision.text
    stable = await client.post(f"/api/v1/cases/{case}/analytics/correlate", json={})
    assert stable.json()["candidates_created"] == stable.json()["candidates_rescored"] == 0
    await upload_text(
        client,
        case,
        "Vendor alias: SYNTHETIC_NORTH\nSYNTHETIC new source\nwickr:synthetic_shared",
        "SYNTHETIC_NEW.html",
    )
    await app.state.jobs.wait_all()
    rescored = await client.post(f"/api/v1/cases/{case}/analytics/correlate", json={})
    assert rescored.json()["candidates_rescored"] == 1, rescored.text
    current = (await client.get(f"/api/v1/cases/{case}/analytics/links")).json()["items"][0]
    assert (
        current["version"] == 2 and current["status"] == "PENDING" and current["decision"] is None
    )
    assert current["supersedes_id"] == original["id"] and current["rescored"]
    historical = (await client.get(f"/api/v1/cases/{case}/analytics/links/{original['id']}")).json()
    assert historical["decision"]["id"] == decision.json()["id"]
    graph = (await client.get(f"/api/v1/cases/{case}/graph")).json()
    assert not any(e["type"] == "ANALYST_CONFIRMED_RELATED" for e in graph["edges"])
    evidence_graph = (
        await client.get(f"/api/v1/cases/{case}/graph", params={"include_evidence": True})
    ).json()
    edge = next(e for e in evidence_graph["edges"] if e["type"] == "CONTAINS")
    proof = await client.get(f"/api/v1/cases/{case}/graph/edges/{edge['id']}/provenance")
    assert proof.status_code == 200 and proof.json()["evidence"]


@pytest.mark.integration
async def test_simultaneous_reviews_and_stale_versions_conflict(app, client, actor_login):
    import asyncio

    await actor_login()
    case = await make_case(client)
    candidate, _, _ = await seed_pair(app, case)
    data = {
        "target_type": "LINK",
        "target_id": str(candidate),
        "decision": "ACCEPT",
        "rationale": "SYNTHETIC review checks same version",
    }
    stale = await client.post(
        f"/api/v1/cases/{case}/decisions", json=data, headers={"If-Match": '"2"'}
    )
    assert stale.status_code == 409, stale.text
    responses = await asyncio.gather(
        *(
            client.post(f"/api/v1/cases/{case}/decisions", json=data, headers={"If-Match": '"1"'})
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in responses) == [201, 409]


@pytest.mark.integration
async def test_profile_attribution_and_utc_trend_diversity(app, client, actor_login):
    import json
    from uuid import UUID

    from darknetra.analytics.profiles import build_profiles

    await actor_login()
    case = await make_case(client)
    day = datetime.now(UTC).date().isoformat()
    messages = [
        {
            "id": i + 1,
            "type": "message",
            "date": f"{day}T10:0{i}:00+00:00",
            "from": f"SYNTHETIC_SENDER_{i % 2}",
            "text": f"SYNTHETIC chitta observation wickr:synthetic_contact_{i % 2}",
        }
        for i in range(4)
    ]
    evidence = await upload_text(
        client, case, json.dumps({"name": "SYNTHETIC", "messages": messages}), "SYNTHETIC.json"
    )
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        profiles = await build_profiles(db, UUID(case), app.state.settings)
        assert len(profiles) == 2
        a = next(p for p in profiles if p.value == "synthetic_sender_0")
        b = next(p for p in profiles if p.value == "synthetic_sender_1")
        assert a.contacts and b.contacts and not (set(a.contacts) & set(b.contacts))
        assert all(ids == {UUID(evidence["id"])} for ids in a.contacts.values())
    response = await client.get(
        f"/api/v1/cases/{case}/trends", params={"term": "heroin", "window_days": 1}
    )
    assert response.status_code == 200, response.text
    series = response.json()["series"][0]
    assert series["candidate"] is True
    assert series["points"][0]["count"] == 4
    assert series["points"][0]["unique_aliases"] == 2
    assert series["points"][0]["unique_sources"] == 1


@pytest.mark.integration
async def test_cross_case_graph_candidates_and_decisions_are_hidden(app, client, actor_login):
    await actor_login()
    case = await make_case(client)
    other = await make_case(client, "SYNTHETIC case boundary")
    candidate, _, subjects = await seed_pair(app, case)
    data = {
        "target_type": "LINK",
        "target_id": str(candidate),
        "decision": "ACCEPT",
        "rationale": "SYNTHETIC review evidence scope check",
    }
    accepted = await client.post(f"/api/v1/cases/{case}/decisions", json=data)
    assert accepted.status_code == 201
    graph = (await client.get(f"/api/v1/cases/{case}/graph")).json()
    edge = graph["edges"][0]
    for path in (
        f"analytics/links/{candidate}",
        f"graph?focus={subjects[0]}",
        f"graph/edges/{edge['id']}/provenance",
    ):
        hidden = await client.get(f"/api/v1/cases/{other}/{path}")
        assert hidden.status_code == 404, (path, hidden.text)
    denied = await client.post(f"/api/v1/cases/{other}/decisions", json=data)
    assert denied.status_code == 404
    assert (await client.get(f"/api/v1/cases/{other}/decisions")).json()["items"] == []


@pytest.mark.integration
async def test_finding_supersession_preserves_claim_and_demands_fresh_review(
    app, client, actor_login
):
    from uuid import UUID

    from darknetra.api.v1.schemas.findings import FindingCreate
    from darknetra.auth.actor import Actor
    from darknetra.cases.models import Case
    from darknetra.decisions.models import Finding
    from darknetra.decisions.service import supersede_finding

    user = await actor_login()
    case = await make_case(client)
    await seed_pair(app, case)
    body = {
        "title": "SYNTHETIC finding",
        "claim": "SYNTHETIC original claim",
        "evidence_codes": ["E-0001"],
        "method": "review",
        "kind_hint": "OBSERVED",
    }
    response = await client.post(f"/api/v1/cases/{case}/findings", json=body)
    assert response.status_code == 201
    fid = response.json()["id"]
    body["claim"] = "SYNTHETIC revised claim"
    async with app.state.session_factory() as db:
        row = await db.scalar(select(Case).where(Case.id == UUID(case)))
        replacement = await supersede_finding(
            db,
            case=row,
            actor=Actor("USER", user.id, user.global_role, user_id=user.id),
            finding_id=UUID(fid),
            data=FindingCreate.model_validate(body),
        )
        assert replacement.version == 2 and replacement.supersedes_id == UUID(fid)
        assert replacement.status == "DRAFT" and replacement.decision_id is None
        original = await db.scalar(
            select(Finding).where(Finding.case_id == UUID(case), Finding.id == UUID(fid))
        )
        assert original.claim == "SYNTHETIC original claim" and original.status == "SUPERSEDED"
        await db.commit()


@pytest.mark.integration
async def test_activity_does_not_combine_signals_from_different_senders(app, client, actor_login):
    import json

    await actor_login()
    case = await make_case(client)
    day = datetime.now(UTC).date().isoformat()
    messages = [
        {
            "id": 1,
            "type": "message",
            "date": f"{day}T10:00:00+00:00",
            "from": "SYNTHETIC_A",
            "text": "SYNTHETIC chitta",
        },
        {
            "id": 2,
            "type": "message",
            "date": f"{day}T10:01:00+00:00",
            "from": "SYNTHETIC_B",
            "text": "SYNTHETIC available 5 gm INR 2500 shipping delivery wickr:synthetic_b",
        },
    ]
    evidence = await upload_text(
        client,
        case,
        json.dumps({"name": "SYNTHETIC", "messages": messages}),
        "SYNTHETIC_ACTIVITY.json",
    )
    await app.state.jobs.wait_all()
    response = await client.post(f"/api/v1/cases/{case}/analytics/correlate", json={})
    assert response.status_code == 200, response.text
    activities = (await client.get(f"/api/v1/cases/{case}/analytics/activity")).json()["items"]
    activity = next(a for a in activities if a["evidence"]["id"] == evidence["id"])
    assert activity["score"] <= 0.65
    assert activity["label"] != "HIGH_PRIORITY_REVIEW"


@pytest.mark.integration
async def test_activity_review_rejects_superseded_candidate_version(app, client, actor_login):
    from uuid import UUID

    from darknetra.analytics.models import ActivityCandidate, LinkCandidate

    await actor_login()
    case = await make_case(client)
    candidate_id, evidence_id, _ = await seed_pair(app, case)
    async with app.state.session_factory() as db:
        pair = await db.scalar(
            select(LinkCandidate).where(
                LinkCandidate.case_id == UUID(case), LinkCandidate.id == candidate_id
            )
        )
        versions = [
            ActivityCandidate(
                id=uuid4(),
                case_id=UUID(case),
                run_id=pair.run_id,
                evidence_id=evidence_id,
                score=0.2,
                label="LOW_SIGNAL",
                features=[],
                status="PENDING",
                version=v,
            )
            for v in (1, 2)
        ]
        db.add_all(versions)
        await db.commit()
    response = await client.post(
        f"/api/v1/cases/{case}/decisions",
        json={
            "target_type": "ACTIVITY",
            "target_id": str(versions[0].id),
            "decision": "ACCEPT",
            "rationale": "SYNTHETIC review attempted on stale activity",
        },
    )
    assert response.status_code == 409, response.text
