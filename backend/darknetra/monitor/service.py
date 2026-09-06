"""Watchlist mutations, serialized within their case and always audited."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from darknetra.api.v1.schemas import watchlists as dto
from darknetra.audit.service import record
from darknetra.auth.models import User
from darknetra.cases.models import Case
from darknetra.cases.service import ensure_open
from darknetra.errors import Conflict, NotFound, Validation
from darknetra.evidence.models import Derivative, Evidence
from darknetra.evidence.vault import LocalVault
from darknetra.monitor.models import Watchlist, WatchlistItem
from darknetra.monitor.validation import DEFAULTS, sources_for, validate_item


async def get_watchlist(db, case_id, wid):
    row = await db.scalar(
        select(Watchlist).where(Watchlist.case_id == case_id, Watchlist.id == wid)
    )
    if not row:
        raise NotFound("Watchlist not found")
    return row


async def get_item(db, case_id, wid, iid, *, lock=False):
    query = select(WatchlistItem).where(
        WatchlistItem.case_id == case_id, WatchlistItem.watchlist_id == wid, WatchlistItem.id == iid
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if not row:
        raise NotFound("Watchlist item not found")
    return row


async def watchlist_dto(db, row):
    user = await db.get(User, row.created_by)
    return dto.Watchlist(
        id=row.id,
        case_id=row.case_id,
        name=row.name,
        active=row.active,
        created_by={
            "kind": "USER",
            "id": row.created_by,
            "display": user.display_name if user else "User",
        },
        created_at=row.created_at,
    )


async def lock_case(db, case):
    locked = await db.scalar(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ensure_open(locked)
    return locked


async def create_watchlist(db, case, actor, name):
    await lock_case(db, case)
    if not name.strip():
        raise Validation("Watchlist name cannot be blank")
    row = Watchlist(case_id=case.id, name=name.strip(), created_by=actor.user_id)
    db.add(row)
    await db.flush()
    await record(
        db,
        actor=actor,
        action="watchlist.create",
        case_id=case.id,
        target_type="watchlist",
        target_id=row.id,
    )
    return row


async def resolve_image(db, case_id, value, settings):
    if not value.startswith("E-"):
        return value
    evidence = await db.scalar(
        select(Evidence).where(
            Evidence.case_id == case_id,
            Evidence.code == value,
            Evidence.kind == "IMAGE",
            Evidence.status.in_(["READY", "PARTIAL"]),
        )
    )
    derivative = (
        await db.scalar(
            select(Derivative)
            .where(
                Derivative.case_id == case_id,
                Derivative.evidence_id == evidence.id,
                Derivative.kind == "IMAGE_META",
            )
            .order_by(Derivative.version.desc())
            .limit(1)
        )
        if evidence
        else None
    )
    if not derivative:
        raise Validation("Image evidence hash is unavailable")
    import json

    with LocalVault(settings.vault_path).open(derivative.storage_key) as stream:
        data = json.load(stream)
    value = data.get("phash") or data.get("pHash")
    if not value:
        raise Validation("Image evidence hash is unavailable")
    return value


async def create_item(db, case, wid, actor, body, settings):
    case = await lock_case(db, case)
    watchlist = await get_watchlist(db, case.id, wid)
    if not watchlist.active:
        raise Conflict("Watchlist is inactive")
    value = (
        await resolve_image(db, case.id, body.value, settings)
        if body.type == "IMAGE_HASH"
        else body.value
    )
    value_norm, variants = validate_item(body.type, value, body.variants)
    existing = await db.scalar(
        select(WatchlistItem.id).where(
            WatchlistItem.case_id == case.id,
            WatchlistItem.type == body.type,
            WatchlistItem.value_norm == value_norm,
        )
    )
    if existing:
        raise Conflict("This item already exists in the case")
    interval = (
        body.interval_seconds
        if "interval_seconds" in body.model_fields_set
        else DEFAULTS[body.type][1]
    )
    row = WatchlistItem(
        id=uuid4(),
        case_id=case.id,
        watchlist_id=wid,
        type=body.type,
        value=value,
        value_norm=value_norm,
        variants=variants,
        sources=sources_for(body.type, body.sources, case, settings),
        interval_seconds=interval,
        active=body.active,
        note=body.note,
        state={},
        next_run_at=datetime.now(UTC) + timedelta(seconds=effective_interval(interval, settings)),
        created_by=actor.user_id,
    )
    db.add(row)
    await db.flush()
    await record(
        db,
        actor=actor,
        action="watchlist.item_create",
        case_id=case.id,
        target_type="watchlist_item",
        target_id=row.id,
        detail={"type": row.type, "sources": row.sources},
    )
    return row


def effective_interval(interval, settings):
    return settings.monitor_interval_override or (120 if settings.demo_mode else interval)


async def patch_item(db, case, wid, iid, actor, body, settings):
    case = await lock_case(db, case)
    row = await get_item(db, case.id, wid, iid, lock=True)
    changes = body.model_dump(exclude_unset=True)
    if any(
        changes.get(k) is None
        for k in {"value", "variants", "sources", "interval_seconds", "active"} & changes.keys()
    ):
        raise Validation("Only note may be cleared")
    if "value" in changes and changes["value"] != row.value:
        # Histories and seen hashes belong to one identity; replacement is a new item.
        raise Conflict("Deactivate this item and create a new item to change its value")
    if "variants" in changes:
        _, changes["variants"] = validate_item(row.type, row.value, changes["variants"])
    if "sources" in changes:
        changes["sources"] = sources_for(row.type, changes["sources"], case, settings)
    for key, value in changes.items():
        setattr(row, key, value)
    row.next_run_at = (
        datetime.now(UTC) + timedelta(seconds=effective_interval(row.interval_seconds, settings))
        if row.active
        else None
    )
    await record(
        db,
        actor=actor,
        action="watchlist.item_update",
        case_id=case.id,
        target_type="watchlist_item",
        target_id=row.id,
        detail={"fields": sorted(changes)},
    )
    return row
