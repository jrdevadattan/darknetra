"""Retention expires visibility; original bytes and provenance are preserved."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from darknetra.audit.service import record
from darknetra.cases.models import Case
from darknetra.errors import NotFound
from darknetra.evidence.models import Evidence


async def expire(db, *, case_id, actor, now=None):
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if case is None:
        raise NotFound("Case not found")
    days = case.source_policy.get("retention_days")
    if case.legal_hold or not days:
        return []
    threshold = (now or datetime.now(UTC)) - timedelta(days=days)
    rows = list(
        await db.scalars(
            select(Evidence)
            .where(
                Evidence.case_id == case_id,
                Evidence.captured_at < threshold,
                Evidence.status.in_(["READY", "PARTIAL"]),
            )
            .order_by(Evidence.code)
        )
    )
    for row in rows:
        row.status = "EXPIRED"
        await record(
            db,
            actor=actor,
            action="evidence.expired",
            case_id=case_id,
            target_type="evidence",
            target_id=row.id,
            detail={"retention_days": days, "bytes_preserved": True},
            result_hash=row.sha256,
        )
    return rows
