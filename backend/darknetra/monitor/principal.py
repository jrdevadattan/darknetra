"""Persist suspension instead of silently dropping schedules whose authority was revoked."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.auth.service import user_actor
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.cases.models import Case
from darknetra.errors import AppError, PolicyDenied
from darknetra.monitor.alerts import raise_alert
from darknetra.monitor.models import Alert, MonitorRun, WatchlistItem
from darknetra.monitor.service import effective_interval
from darknetra.policy.actor import refresh_actor
from darknetra.tools.contracts import ToolError


async def require_execution_actor(session_factory, *, case_id, actor):
    """Recheck current authority before publishing a long-running collection."""
    async with session_factory() as db:
        try:
            current = await refresh_actor(db, actor)
            case, role = await visible_case(db, current, case_id)
            if (
                case.status != "OPEN"
                or not permitted(current.global_role, role, Permission.WATCHLIST_MANAGE)
                or (
                    current.kind == "TOKEN"
                    and not scope_permits(current.scopes, Permission.WATCHLIST_MANAGE)
                )
            ):
                raise PolicyDenied("Monitoring execution authority is no longer active")
            return current
        except (ToolError, AppError) as exc:
            raise PolicyDenied("Monitoring execution authority is no longer active") from exc


async def execution_actor(db, *, case_id, user_id, settings, item=None):
    user = await db.get(User, user_id)
    if user and user.is_active and not user.must_change_password:
        actor = user_actor(user)
        try:
            _, role = await visible_case(db, actor, case_id)
            if permitted(actor.global_role, role, Permission.WATCHLIST_MANAGE):
                return actor
        except AppError:
            pass
    # SYSTEM records an operational denial only; it does not borrow user authority to fetch.
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not case or case.status != "OPEN":
        return None
    if item is not None:
        item = await db.scalar(
            select(WatchlistItem)
            .where(WatchlistItem.case_id == case_id, WatchlistItem.id == item.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None or not item.active:
            return None
    now = datetime.now(UTC)
    actor = Actor("SYSTEM", None)
    error = {
        "code": "POLICY_DENIED",
        "message": "Monitoring execution user is no longer authorised",
    }
    if item is not None:
        run = MonitorRun(
            case_id=case_id,
            item_id=item.id,
            status="ERROR",
            started_at=now,
            finished_at=now,
            manual=False,
            sources_run={"execution_principal": {"status": "DENIED"}},
            new_hits=0,
            errors={"execution_principal": error},
        )
        db.add(run)
        await db.flush()
        item.last_run_at = now
        item.next_run_at = now + timedelta(
            seconds=effective_interval(item.interval_seconds, settings)
        )
        item.state = {
            **item.state,
            "last_run_id": str(run.id),
            "last_status": "ERROR",
            "suspension_reason": error["message"],
        }
    previous = await db.scalar(
        select(Alert.id).where(
            Alert.case_id == case_id,
            Alert.kind == "MONITOR_ERROR",
            Alert.item_id == (item.id if item else None),
            Alert.at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
            Alert.diversity["source"].astext == "execution_principal",
        )
    )
    if not previous:
        await raise_alert(
            db,
            case_id=case_id,
            actor=actor,
            kind="MONITOR_ERROR",
            title="Monitoring authority requires attention",
            summary=error["message"],
            evidence_ids=[],
            item_id=item.id if item else None,
            diversity={"source": "execution_principal", "error_code": "POLICY_DENIED"},
        )
    await record(
        db,
        actor=actor,
        action="monitor.suspended",
        case_id=case_id,
        target_type="watchlist_item" if item else "case",
        target_id=item.id if item else case_id,
        detail={"code": "POLICY_DENIED", "execution_user_id": str(user_id)},
    )
    return None
