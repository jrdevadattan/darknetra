"""APScheduler reconciliation and spaced restart catch-up over persisted due times."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.auth.service import user_actor
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted
from darknetra.cases.models import Case
from darknetra.errors import AppError
from darknetra.monitor.models import Watchlist, WatchlistItem
from darknetra.monitor.runner import run_item
from darknetra.monitor.service import effective_interval

log = logging.getLogger(__name__)


def catch_up_times(items, now):
    return {
        item.id: now + timedelta(seconds=5 * index)
        for index, item in enumerate(
            sorted(items, key=lambda item: (item.next_run_at or now, str(item.id)))
        )
    }


class MonitorScheduler:
    def __init__(self, app, scheduler):
        self.app, self.scheduler = app, scheduler
        self.signatures = {}

    async def run_now(self, case_id, item_id):
        async def work():
            async with self.app.state.session_factory() as db:
                item = await db.scalar(
                    select(WatchlistItem).where(
                        WatchlistItem.case_id == case_id, WatchlistItem.id == item_id
                    )
                )
                if not item:
                    return
                user = await db.get(User, item.created_by)
                if not user or not user.is_active or user.must_change_password:
                    return
                actor = user_actor(user)
                try:
                    _, role = await visible_case(db, actor, case_id)
                    if not permitted(actor.global_role, role, Permission.WATCHLIST_MANAGE):
                        return
                    await run_item(
                        db,
                        case_id=case_id,
                        item_id=item_id,
                        actor=actor,
                        settings=self.app.state.settings,
                        session_factory=self.app.state.session_factory,
                    )
                    await db.commit()
                except AppError:
                    await db.rollback()
                    log.info("monitor_tick_skipped case_id=%s item_id=%s", case_id, item_id)

        return await self.app.state.jobs.submit(
            "monitor.run", work, key=f"monitor:{case_id}:{item_id}"
        )

    def remove_item(self, item_id):
        key = str(item_id)
        if self.scheduler.get_job(key):
            self.scheduler.remove_job(key)
        self.signatures.pop(key, None)

    def add_item(self, item, next_run_time=None):
        interval = effective_interval(item.interval_seconds, self.app.state.settings)
        self.scheduler.add_job(
            self.run_now,
            trigger=IntervalTrigger(seconds=interval, jitter=int(interval * 0.1)),
            args=[item.case_id, item.id],
            id=str(item.id),
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
            next_run_time=next_run_time or item.next_run_at or datetime.now(UTC),
        )
        self.signatures[str(item.id)] = (item.updated_at, interval)

    async def catch_up(self):
        await self.reconcile()

    async def trends(self):
        from darknetra.monitor.trends_bridge import promote_candidates

        async with self.app.state.session_factory() as db:
            cases = list(await db.scalars(select(Case).where(Case.status == "OPEN")))
        for case in cases:
            async with self.app.state.session_factory() as db:
                user = await db.get(User, case.created_by)
                if not user or not user.is_active or user.must_change_password:
                    continue
                actor = user_actor(user)
                try:
                    _, role = await visible_case(db, actor, case.id)
                    if not permitted(actor.global_role, role, Permission.WATCHLIST_MANAGE):
                        continue
                    await promote_candidates(db, case=case, actor=actor)
                    await db.commit()
                except AppError:
                    await db.rollback()

    async def retention(self):
        from darknetra.monitor.retention import expire

        async with self.app.state.session_factory() as db:
            case_ids = list(await db.scalars(select(Case.id).where(Case.legal_hold.is_(False))))
        for case_id in case_ids:
            async with self.app.state.session_factory() as db:
                await expire(db, case_id=case_id, actor=Actor("SYSTEM", None))
                await db.commit()

    async def reconcile(self):
        async with self.app.state.session_factory() as db:
            items = list(
                await db.scalars(
                    select(WatchlistItem)
                    .join(Case, Case.id == WatchlistItem.case_id)
                    .join(
                        Watchlist,
                        (Watchlist.id == WatchlistItem.watchlist_id)
                        & (Watchlist.case_id == WatchlistItem.case_id),
                    )
                    .where(
                        WatchlistItem.active.is_(True),
                        Watchlist.active.is_(True),
                        Case.status == "OPEN",
                    )
                )
            )
        now = datetime.now(UTC)
        catch_up = catch_up_times(
            [i for i in items if not i.next_run_at or i.next_run_at <= now], now
        )
        active = {str(i.id) for i in items}
        for item_id in set(self.signatures) - active:
            self.remove_item(item_id)
        for item in items:
            signature = (
                item.updated_at,
                effective_interval(item.interval_seconds, self.app.state.settings),
            )
            if self.signatures.get(str(item.id)) != signature or not self.scheduler.get_job(
                str(item.id)
            ):
                self.add_item(item, catch_up.get(item.id))


def configure(app, scheduler):
    monitor = MonitorScheduler(app, scheduler)
    app.state.monitor = monitor
    scheduler.add_job(
        monitor.reconcile,
        "interval",
        seconds=15,
        id="monitor:reconcile",
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.now(UTC),
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        monitor.trends,
        "interval",
        days=1,
        id="monitor:trends",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        monitor.retention,
        "interval",
        days=1,
        id="monitor:retention",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
