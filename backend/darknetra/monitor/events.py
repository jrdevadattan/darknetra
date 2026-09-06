"""Image ingestion hook. Dispatch occurs only after the evidence commit."""

from sqlalchemy import select

from darknetra.auth.models import User
from darknetra.auth.service import user_actor
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted
from darknetra.evidence.models import Evidence
from darknetra.monitor.models import WatchlistItem
from darknetra.monitor.runner import run_item


async def on_evidence(app, case_id, evidence_id):
    async with app.state.session_factory() as db:
        evidence = await db.scalar(
            select(Evidence).where(
                Evidence.case_id == case_id,
                Evidence.id == evidence_id,
                Evidence.kind == "IMAGE",
                Evidence.status.in_(["READY", "PARTIAL"]),
            )
        )
        if not evidence:
            return []
        items = list(
            await db.scalars(
                select(WatchlistItem).where(
                    WatchlistItem.case_id == case_id,
                    WatchlistItem.type == "IMAGE_HASH",
                    WatchlistItem.active.is_(True),
                )
            )
        )
    job_ids = []
    for item in items:

        async def work(iid=item.id, uid=item.created_by):
            async with app.state.session_factory() as db:
                user = await db.get(User, uid)
                if not user or not user.is_active or user.must_change_password:
                    return
                actor = user_actor(user)
                _, role = await visible_case(db, actor, case_id)
                if not permitted(actor.global_role, role, Permission.WATCHLIST_MANAGE):
                    return
                await run_item(
                    db,
                    case_id=case_id,
                    item_id=iid,
                    actor=actor,
                    settings=app.state.settings,
                    session_factory=app.state.session_factory,
                )
                await db.commit()

        job_ids.append(
            await app.state.jobs.submit("monitor.image", work, key=f"monitor:{case_id}:{item.id}")
        )
    return job_ids
