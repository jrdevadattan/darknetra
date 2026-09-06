import asyncio
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from freezegun import freeze_time
from pypdf import PdfReader
from sqlalchemy import func, select, text

from darknetra.audit.models import AuditEvent
from darknetra.auth.service import user_actor
from darknetra.decisions.models import Decision
from darknetra.evidence.models import Evidence
from darknetra.monitor.alerts import raise_alert
from darknetra.monitor.models import Alert, MonitorHit, MonitorSeenUrl
from darknetra.reports.narrative import checked_narrative

pytestmark = pytest.mark.integration


async def create_case(client):
    response = await client.post(
        "/api/v1/cases",
        json={
            "title": "SYNTHETIC monitoring/report test",
            "demo": True,
            "authority_ref": "SYNTHETIC AUTHORITY",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def add_evidence(client, app, cid, *, family="SYNTHETIC_FAMILY_A", content=None):
    response = await client.post(
        f"/api/v1/cases/{cid}/evidence",
        data={"source_class": "SYNTHETIC", "source_family": family},
        files={
            "files": (
                "synthetic.txt",
                content
                or f"SYNTHETIC {family}: safed line is a synthetic fixture. contact synthetic@example.invalid",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201, response.text
    await app.state.jobs.wait_all()
    return response.json()["results"][0]["evidence"]


async def item(client, cid, *, sources=None, kind="KEYWORD", value="safed line"):
    response = await client.post(
        f"/api/v1/cases/{cid}/watchlists", json={"name": "SYNTHETIC watchlist"}
    )
    assert response.status_code == 201, response.text
    wid = response.json()["id"]
    response = await client.post(
        f"/api/v1/cases/{cid}/watchlists/{wid}/items",
        json={"type": kind, "value": value, "sources": sources or ["evidence"]},
    )
    assert response.status_code == 201, response.text
    return wid, response.json()["id"]


async def test_monitor_persisted_dedupe_alert_escalation_and_case_isolation(
    client, app, actor_login
):
    await actor_login()
    cid = await create_case(client)
    first = await add_evidence(client, app, cid)
    second = await add_evidence(client, app, cid, family="SYNTHETIC_FAMILY_B")
    wid, iid = await item(client, cid)
    url = f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run"
    response = await asyncio.wait_for(client.post(url), timeout=15)
    assert response.status_code == 200, response.text
    assert response.json()["new_hits"] == 2
    assert response.json()["status"] == "DONE"
    response = await client.post(url)
    assert response.json()["new_hits"] == 0
    response = await client.get(f"/api/v1/cases/{cid}/alerts")
    alerts = response.json()["items"]
    assert len(alerts) == 1 and alerts[0]["status"] == "OPEN"
    assert alerts[0]["evidence"][0]["id"] in {first["id"], second["id"]}
    aid = alerts[0]["id"]
    stale = await client.post(
        f"/api/v1/cases/{cid}/alerts/{aid}/escalate",
        json={"rationale": "SYNTHETIC analyst review"},
        headers={"If-Match": '"2"'},
    )
    assert stale.status_code == 409
    response = await client.post(
        f"/api/v1/cases/{cid}/alerts/{aid}/escalate", json={"rationale": "SYNTHETIC analyst review"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["alert"]["status"] == "ESCALATED"
    assert response.json()["finding"]["kind"] == "CANDIDATE"
    assert response.json()["finding"]["status"] == "DRAFT"
    repeat = await client.post(
        f"/api/v1/cases/{cid}/alerts/{aid}/dismiss", json={"rationale": "SYNTHETIC repeat"}
    )
    assert repeat.status_code == 409
    changed = await client.get(
        f"/api/v1/cases/{cid}/changes",
        params={"since": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["hits"] == 2 and len(changed.json()["decisions"]) == 1
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MonitorSeenUrl)
                .where(MonitorSeenUrl.case_id == UUID(cid))
            )
            == 2
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Decision)
                .where(Decision.case_id == UUID(cid), Decision.target_type == "ALERT")
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.case_id == UUID(cid), AuditEvent.action == "alert.escalate")
            )
            == 1
        )
    foreign = await create_case(client)
    assert (await client.get(f"/api/v1/cases/{foreign}/watchlists/{wid}/items")).status_code == 404
    await actor_login()
    assert (await client.get(f"/api/v1/cases/{cid}/alerts")).status_code == 404


async def test_offline_network_errors_are_persisted_and_never_fake_hits(client, app, actor_login):
    await actor_login()
    cid = await create_case(client)
    wid, iid = await item(client, cid, sources=["web_search"])
    response = await client.post(f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run")
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "ERROR" and run["new_hits"] == 0
    assert run["errors"]["web_search"]["code"] == "NETWORK_REQUIRED"
    assert (await client.get(f"/api/v1/cases/{cid}/evidence")).json()["items"] == []
    assert (await client.delete(f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}")).json()[
        "active"
    ] is False
    assert (
        await client.post(f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run")
    ).status_code == 409


async def test_scenario_31_hourly_overflow_and_evidence_validation(client, app, actor_login):
    user = await actor_login()
    cid = UUID(await create_case(client))
    evidence = await add_evidence(client, app, cid)
    async with app.state.session_factory() as db:
        for index in range(24):
            await raise_alert(
                db,
                case_id=cid,
                actor=user_actor(user),
                kind="NEW_HIT",
                title="SYNTHETIC alert",
                summary=f"SYNTHETIC review {index}",
                evidence_ids=[UUID(evidence["id"])],
            )
        await db.commit()
        alerts = list(await db.scalars(select(Alert).where(Alert.case_id == cid)))
        assert len(alerts) == 21
        overflow = next(a for a in alerts if a.kind == "OVERFLOW")
        assert overflow.diversity["overflow_count"] == 4
        assert overflow.evidence_ids == [UUID(evidence["id"])]


async def test_report_pdf_zip_manifest_versioning_redaction_and_immutability(
    client, app, actor_login
):
    await actor_login()
    cid = await create_case(client)
    evidence = await add_evidence(
        client,
        app,
        cid,
        content="SYNTHETIC source: safed line; synthetic@example.invalid; +91 9876543210",
    )
    response = await client.post(f"/api/v1/cases/{cid}/reports", json={"narrative": True})
    assert response.status_code == 202, response.text
    rid = response.json()["report_id"]
    await app.state.jobs.wait_all()
    response = await client.get(f"/api/v1/cases/{cid}/reports/{rid}")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["status"] == "DONE", report
    assert report["evidence"]["code"] != evidence["code"]
    downloaded = {}
    for fmt in ["md", "html", "pdf", "zip", "sha256", "manifest"]:
        response = await client.get(
            f"/api/v1/cases/{cid}/reports/{rid}/download", params={"format": fmt}
        )
        assert response.status_code == 200, response.text
        downloaded[fmt] = response.content
    assert hashlib.sha256(downloaded["zip"]).hexdigest() == report["sha256"]
    assert downloaded["sha256"].decode().startswith(report["sha256"])
    assert evidence["code"] in downloaded["md"].decode()
    assert "Evidence appendix" in downloaded["md"].decode()
    assert "synthetic@example.invalid" not in downloaded["md"].decode()
    assert "9876543210" not in downloaded["md"].decode()
    assert "SYNTHETIC AUTHORITY" not in downloaded["md"].decode()
    assert PdfReader(io.BytesIO(downloaded["pdf"])).pages
    with zipfile.ZipFile(io.BytesIO(downloaded["zip"])) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for artifact in manifest["artifacts"]:
            assert hashlib.sha256(archive.read(artifact["name"])).hexdigest() == artifact["sha256"]
    again = await client.post(f"/api/v1/cases/{cid}/reports", json={"narrative": False})
    await app.state.jobs.wait_all()
    version2 = (await client.get(f"/api/v1/cases/{cid}/reports/{again.json()['report_id']}")).json()
    assert version2["version"] == 2 and version2["sha256"] != report["sha256"]
    assert (
        await client.get(f"/api/v1/cases/{cid}/reports/{rid}/download", params={"format": "zip"})
    ).content == downloaded["zip"]
    async with app.state.session_factory() as db:
        with pytest.raises(Exception, match="immutable"):
            await db.execute(
                text("UPDATE reports SET sha256='tampered' WHERE case_id=:cid AND id=:rid"),
                {"cid": UUID(cid), "rid": UUID(rid)},
            )
        await db.rollback()
    foreign = await create_case(client)
    assert (await client.get(f"/api/v1/cases/{foreign}/reports/{rid}")).status_code == 404


async def test_scenario_36_bad_narrative_is_dropped(client, app, actor_login):
    await actor_login()
    cid = await create_case(client)
    evidence = await add_evidence(client, app, cid)
    async with app.state.session_factory() as db:
        accepted, dropped = await checked_narrative(
            db,
            UUID(cid),
            f"The synthetic record exists [{evidence['code']}].\nUnsupported invented claim [E-999999].",
        )
    assert len(accepted) == 1 and len(dropped) == 1
    assert accepted[0]["evidence_codes"] == [evidence["code"]]


async def test_simultaneous_ticks_cannot_create_duplicate_hits(
    client, app, actor_login, monkeypatch
):

    from darknetra.monitor import adapters

    await actor_login()
    cid = await create_case(client)
    await add_evidence(client, app, cid)
    wid, iid = await item(client, cid)
    entered, release = asyncio.Event(), asyncio.Event()
    original = adapters.collect

    async def slow(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    monkeypatch.setattr(adapters, "collect", slow)
    url = f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run"
    first = asyncio.create_task(client.post(url))
    await asyncio.wait_for(entered.wait(), 5)
    second = await asyncio.wait_for(client.post(url), 5)
    assert second.status_code == 429, second.text
    release.set()
    assert (await asyncio.wait_for(first, 10)).json()["new_hits"] == 1
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(MonitorHit).where(MonitorHit.case_id == UUID(cid))
            )
            == 1
        )


async def test_external_capture_does_not_deadlock_and_preserves_requester(
    client, app, actor_login, monkeypatch
):
    from darknetra.evidence.service import ingest_bytes
    from darknetra.monitor import adapters

    await actor_login()
    cid = await create_case(client)
    wid, iid = await item(client, cid, sources=["web_search"])

    # A synthetic adapter models the independent transaction used by capture.gate.
    # It stores actual fixture bytes before returning their evidence reference.
    async def synthetic_capture(db, case, watch, source, ctx):
        async with ctx.session_factory() as captured_db:
            result = await ingest_bytes(
                captured_db,
                case=case,
                actor=ctx.actor,
                data=b"SYNTHETIC captured safed line",
                filename="synthetic-capture.txt",
                settings=ctx.settings,
                source_class="SYNTHETIC",
                origin="MONITOR",
                requester_kind="WATCHLIST_ITEM",
                requester_id=watch.id,
                meta={"source_family": "SYNTHETIC_CAPTURE"},
            )
            await captured_db.commit()
        evidence = result.evidence
        return [
            adapters.Hit(
                evidence.id,
                evidence.code,
                "SYNTHETIC captured safed line",
                "SYNTHETIC",
                "https://synthetic.invalid/capture",
                evidence.sha256,
                "SYNTHETIC_CAPTURE",
            )
        ]

    monkeypatch.setattr(adapters, "collect", synthetic_capture)
    response = await asyncio.wait_for(
        client.post(f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run"), 10
    )
    assert response.status_code == 200, response.text
    assert response.json()["new_hits"] == 1
    async with app.state.session_factory() as db:
        evidence = await db.scalar(select(Evidence).where(Evidence.case_id == UUID(cid)))
        assert evidence.requested_by_kind == "WATCHLIST_ITEM" and evidence.requested_by_id == UUID(
            iid
        )
        assert evidence.origin == "MONITOR" and evidence.source_class == "SYNTHETIC"


async def test_three_failures_raise_one_error_alert_and_rate_limits_do_not_count(
    client, app, actor_login, monkeypatch
):
    from darknetra.monitor import adapters
    from darknetra.tools.contracts import ToolError

    await actor_login()
    cid = await create_case(client)
    wid, iid = await item(client, cid)
    failure = {"code": "UNAVAILABLE"}

    async def unavailable(*args):
        raise ToolError(failure["code"], "SYNTHETIC provider unavailable", {"retry_after": 300})

    monkeypatch.setattr(adapters, "collect", unavailable)
    url = f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run"
    start = datetime.now(UTC)
    for elapsed in (0, 61, 182, 423):
        with freeze_time(start + timedelta(seconds=elapsed), real_asyncio=True):
            response = await client.post(url)
            assert response.status_code == 200
            assert (await client.post(url)).status_code == 429
    alerts = (await client.get(f"/api/v1/cases/{cid}/alerts")).json()["items"]
    assert len(alerts) == 1 and alerts[0]["kind"] == "MONITOR_ERROR"
    failure["code"] = "RATE_LIMITED"
    assert (await client.post(url)).status_code == 429


async def test_scheduled_run_and_image_event_use_persisted_items(client, app, actor_login):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from PIL import Image

    from darknetra.monitor.events import on_evidence
    from darknetra.monitor.models import WatchlistItem
    from darknetra.monitor.scheduler import MonitorScheduler

    await actor_login()
    cid = await create_case(client)
    await add_evidence(client, app, cid)
    await add_evidence(client, app, cid, family="SYNTHETIC_FAMILY_B")
    _, iid = await item(client, cid)
    scheduler = AsyncIOScheduler(timezone="UTC")
    monitor = MonitorScheduler(app, scheduler)
    await monitor.run_now(UUID(cid), UUID(iid))
    await app.state.jobs.wait_all()
    assert (await client.get(f"/api/v1/cases/{cid}/alerts")).json()["items"]
    async with app.state.session_factory() as db:
        stored = await db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.case_id == UUID(cid), WatchlistItem.id == UUID(iid)
            )
        )
        monitor.add_item(stored)
    scheduled = scheduler.get_job(iid)
    assert scheduled.max_instances == 1 and scheduled.coalesce
    assert scheduled.trigger.interval.total_seconds() == 120
    _, image_iid = await item(client, cid, kind="IMAGE_HASH", value="8000000000000000")
    image = Image.new("RGB", (32, 32), "white")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    response = await client.post(
        f"/api/v1/cases/{cid}/evidence",
        data={"source_class": "SYNTHETIC"},
        files={"files": ("SYNTHETIC.png", image_bytes.getvalue(), "image/png")},
    )
    await app.state.jobs.wait_all()
    eid = UUID(response.json()["results"][0]["evidence"]["id"])
    await on_evidence(app, UUID(cid), eid)
    await app.state.jobs.wait_all()
    hits = (
        await client.get(f"/api/v1/cases/{cid}/monitor/hits", params={"item_id": image_iid})
    ).json()["items"]
    assert len(hits) == 1 and hits[0]["alertable"]


async def test_report_unredacted_permission_and_failed_job_state(
    client, app, actor_login, monkeypatch
):
    from darknetra.cases.models import CaseMembership
    from darknetra.reports import service as report_service

    user = await actor_login()
    cid = await create_case(client)
    await add_evidence(client, app, cid)
    response = await client.post(
        f"/api/v1/cases/{cid}/reports", json={"redact": False, "narrative": False}
    )
    await app.state.jobs.wait_all()
    rid = response.json()["report_id"]
    report = (await client.get(f"/api/v1/cases/{cid}/reports/{rid}")).json()
    assert report["status"] == "DONE"
    async with app.state.session_factory() as db:
        membership = await db.get(CaseMembership, (UUID(cid), user.id))
        membership.role = "ANALYST"
        await db.commit()
    assert (
        await client.post(f"/api/v1/cases/{cid}/reports", json={"redact": False})
    ).status_code == 403
    assert (await client.get(f"/api/v1/cases/{cid}/reports/{rid}/download")).status_code == 403
    assert (
        await client.get(f"/api/v1/cases/{cid}/evidence/{report['evidence']['id']}/original")
    ).status_code == 403

    async def failed(*args, **kwargs):
        raise RuntimeError("SYNTHETIC renderer failure")

    monkeypatch.setattr(report_service, "complete", failed)
    response = await client.post(f"/api/v1/cases/{cid}/reports", json={})
    await app.state.jobs.wait_all()
    rid = response.json()["report_id"]
    report = (await client.get(f"/api/v1/cases/{cid}/reports/{rid}")).json()
    assert report["status"] == "ERROR" and report["evidence"] is None and report["sha256"] is None
    assert (await client.get(f"/api/v1/cases/{cid}/reports/{rid}/download")).status_code == 409


async def test_retention_preserves_bytes_and_honors_legal_hold(client, app, actor_login):
    from darknetra.cases.models import Case
    from darknetra.evidence.vault import LocalVault
    from darknetra.monitor.retention import expire

    user = await actor_login()
    cid = UUID(await create_case(client))
    uploaded = await add_evidence(client, app, cid)
    async with app.state.session_factory() as db:
        case = await db.get(Case, cid)
        case.source_policy = {**case.source_policy, "retention_days": 1}
        case.legal_hold = True
        await db.commit()
        assert (
            await expire(
                db, case_id=cid, actor=user_actor(user), now=datetime.now(UTC) + timedelta(days=2)
            )
            == []
        )
        case.legal_hold = False
        await db.commit()
        expired = await expire(
            db, case_id=cid, actor=user_actor(user), now=datetime.now(UTC) + timedelta(days=2)
        )
        await db.commit()
        assert len(expired) == 1 and expired[0].status == "EXPIRED"
        assert (
            LocalVault(app.state.settings.vault_path).hash(expired[0].storage_key)
            == uploaded["sha256"]
        )


async def test_report_omits_foreign_and_unconfirmed_finding_snapshots(client, app, actor_login):
    from darknetra.decisions.models import Finding

    user = await actor_login()
    cid = UUID(await create_case(client))
    same = await add_evidence(client, app, cid)
    foreign_id = UUID(await create_case(client))
    foreign = await add_evidence(client, app, foreign_id)
    async with app.state.session_factory() as db:
        db.add(
            Finding(
                case_id=cid,
                title="SYNTHETIC invalid confirmation",
                claim="SYNTHETIC unearned confirmed claim",
                kind="CONFIRMED",
                status="PROMOTED",
                evidence_ids=[UUID(same["id"])],
                method="synthetic-invalid-fixture",
                version=1,
                created_by=user.id,
            )
        )
        db.add(
            Finding(
                case_id=cid,
                title="SYNTHETIC FOREIGN SECRET",
                claim="SYNTHETIC foreign case claim",
                kind="CANDIDATE",
                status="PROMOTED",
                evidence_ids=[UUID(foreign["id"])],
                method="synthetic-invalid-fixture",
                version=1,
                created_by=user.id,
            )
        )
        await db.commit()
    response = await client.post(f"/api/v1/cases/{cid}/reports", json={"narrative": False})
    await app.state.jobs.wait_all()
    rid = response.json()["report_id"]
    report = (await client.get(f"/api/v1/cases/{cid}/reports/{rid}")).json()
    assert report["status"] == "DONE" and report["claim_check"]["unverified_dropped"] >= 2
    markdown = (await client.get(f"/api/v1/cases/{cid}/reports/{rid}/download")).text
    assert "SYNTHETIC FOREIGN SECRET" not in markdown
    assert "SYNTHETIC unearned confirmed claim" not in markdown


async def test_trend_bridge_uses_evidence_and_dedupes(client, app, actor_login):
    from darknetra.analytics.models import TrendBucket
    from darknetra.cases.models import Case
    from darknetra.monitor.trends_bridge import promote_candidates

    user = await actor_login()
    cid = UUID(await create_case(client))
    evidence = await add_evidence(client, app, cid, content="SYNTHETIC trend observations: chitta")
    async with app.state.session_factory() as db:
        db.add(
            TrendBucket(
                case_id=cid,
                subject_type="SUBSTANCE",
                subject="heroin",
                day=datetime.now(UTC).date(),
                count=10,
                unique_evidence_families=3,
                unique_aliases=2,
                unique_sources=2,
                computed_at=datetime.now(UTC),
            )
        )
        await db.flush()
        case = await db.get(Case, cid)
        first = await promote_candidates(db, case=case, actor=user_actor(user))
        second = await promote_candidates(db, case=case, actor=user_actor(user))
        await db.commit()
        assert len(first) == 1 and second == []
        assert first[0].evidence_ids == [UUID(evidence["id"])]
