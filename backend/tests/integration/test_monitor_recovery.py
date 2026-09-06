"""Persist monitoring attempts before collection and recover without inventing hits."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from darknetra.audit.models import AuditEvent
from darknetra.auth.service import user_actor
from darknetra.monitor.models import MonitorHit, MonitorRun, WatchlistItem
from darknetra.monitor.runner import run_item
from tests.integration.test_monitor_reports_api import create_case, item

pytestmark = pytest.mark.integration


async def test_principal_denial_preserves_concurrent_deactivation(app, client, actor_login):
    from darknetra.auth.models import User
    from darknetra.monitor.principal import execution_actor

    user = await actor_login()
    cid = UUID(await create_case(client))
    _, iid = await item(client, cid)
    iid = UUID(iid)
    async with app.state.session_factory() as stale:
        loaded = await stale.get(WatchlistItem, iid)
        async with app.state.session_factory() as db:
            (await db.get(User, user.id)).is_active = False
            current = await db.get(WatchlistItem, iid)
            current.active = False
            current.next_run_at = None
            current.state = {"source_backoff": {"evidence": "SYNTHETIC newer state"}}
            await db.commit()
        assert (
            await execution_actor(
                stale, case_id=cid, user_id=user.id, settings=app.state.settings, item=loaded
            )
            is None
        )
        await stale.commit()
    async with app.state.session_factory() as db:
        current = await db.get(WatchlistItem, iid)
        assert current.active is False and current.next_run_at is None
        assert current.state == {"source_backoff": {"evidence": "SYNTHETIC newer state"}}
        assert not list(await db.scalars(select(MonitorRun).where(MonitorRun.case_id == cid)))


async def test_revocation_during_collection_prevents_result_publication(
    app, client, actor_login, monkeypatch
):
    from darknetra.auth.models import User
    from darknetra.errors import PolicyDenied

    user = await actor_login()
    cid = UUID(await create_case(client))
    _, iid = await item(client, cid)
    iid = UUID(iid)
    entered, release = asyncio.Event(), asyncio.Event()

    async def collect(*args):
        entered.set()
        await release.wait()
        return []

    monkeypatch.setattr("darknetra.monitor.adapters.collect", collect)

    async def work():
        async with app.state.session_factory() as db:
            await run_item(
                db,
                case_id=cid,
                item_id=iid,
                actor=user_actor(user),
                settings=app.state.settings,
                session_factory=app.state.session_factory,
            )
            await db.commit()

    task = asyncio.create_task(work())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        async with app.state.session_factory() as db:
            (await db.get(User, user.id)).is_active = False
            await db.commit()
        release.set()
        with pytest.raises(PolicyDenied):
            await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with app.state.session_factory() as db:
        run = await db.scalar(select(MonitorRun).where(MonitorRun.case_id == cid))
        assert run.status == "ERROR" and run.new_hits == 0
        assert not list(await db.scalars(select(MonitorHit).where(MonitorHit.case_id == cid)))


async def test_attempt_visible_before_collection_and_cancel_is_persisted(
    app, client, actor_login, monkeypatch
):
    user = await actor_login()
    cid = UUID(await create_case(client))
    wid, iid = await item(client, cid)
    iid = UUID(iid)
    entered = asyncio.Event()

    async def collect(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("darknetra.monitor.adapters.collect", collect)

    async def work():
        async with app.state.session_factory() as db:
            await run_item(
                db,
                case_id=cid,
                item_id=iid,
                actor=user_actor(user),
                settings=app.state.settings,
                session_factory=app.state.session_factory,
            )
            await db.commit()

    task = asyncio.create_task(work())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        rows = (await client.get(f"/api/v1/cases/{cid}/monitor/runs")).json()["items"]
        assert len(rows) == 1 and rows[0]["status"] == "RUNNING"
        response = await client.post(f"/api/v1/cases/{cid}/watchlists/{wid}/items/{iid}/run")
        assert response.status_code == 429
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with app.state.session_factory() as db:
        run = await db.scalar(select(MonitorRun).where(MonitorRun.case_id == cid))
        assert run.status == "ERROR" and run.finished_at is not None
        assert run.errors["execution"]["code"] == "UNAVAILABLE"
        assert run.errors["execution"]["reason"] == "CANCELLED"
        stored_item = await db.get(WatchlistItem, iid)
        assert stored_item.state["last_run_id"] == str(run.id)
        assert stored_item.next_run_at > run.finished_at
        assert not list(await db.scalars(select(MonitorHit).where(MonitorHit.case_id == cid)))
        actions = list(await db.scalars(select(AuditEvent.action).where(AuditEvent.case_id == cid)))
        assert "monitor.started" in actions and "monitor.interrupted" in actions


async def test_restart_recovery_is_scoped_idempotent_and_skips_active_lock(
    app, client, actor_login
):
    from sqlalchemy import func

    from darknetra.monitor.recovery import recover_interrupted_monitors, run_lock_key

    await actor_login()
    cid, other_cid = UUID(await create_case(client)), UUID(await create_case(client))
    _, iid = await item(client, cid)
    _, other_iid = await item(client, other_cid)
    iid, other_iid = UUID(iid), UUID(other_iid)
    before = datetime.now(UTC)
    async with app.state.session_factory() as db:
        for case_id, item_id in ((cid, iid), (other_cid, other_iid)):
            db.add(
                MonitorRun(
                    id=uuid4(),
                    case_id=case_id,
                    item_id=item_id,
                    status="RUNNING",
                    started_at=before - timedelta(minutes=2),
                    manual=False,
                    sources_run={},
                    errors={},
                    new_hits=0,
                )
            )
        await db.commit()
    async with app.state.session_factory() as active, app.state.session_factory() as db:
        await active.scalar(select(func.pg_advisory_xact_lock(run_lock_key(cid, iid))))
        assert (
            await recover_interrupted_monitors(db, cid, settings=app.state.settings, before=before)
            == 0
        )
        await db.commit()
        await active.rollback()
        assert (
            await recover_interrupted_monitors(db, cid, settings=app.state.settings, before=before)
            == 1
        )
        await db.commit()
        assert (
            await recover_interrupted_monitors(db, cid, settings=app.state.settings, before=before)
            == 0
        )
        run = await db.scalar(select(MonitorRun).where(MonitorRun.case_id == cid))
        assert run.status == "ERROR" and run.errors["execution"]["reason"] == "APPLICATION_RESTART"
        assert (
            await db.scalar(select(MonitorRun).where(MonitorRun.case_id == other_cid))
        ).status == "RUNNING"
