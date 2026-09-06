from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.analytics.graph import latest_links
from darknetra.analytics.models import LinkCandidate
from darknetra.api.v1.schemas.common import FindingRef
from darknetra.api.v1.schemas.digest import CaseDigest
from darknetra.audit.service import record
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.decisions.models import Finding
from darknetra.errors import Validation
from darknetra.evidence.models import Evidence
from darknetra.monitor.alerts import alert_dto
from darknetra.monitor.models import Alert, MonitorHit

router = APIRouter(tags=["cases"])


@router.get("/cases/{case_id}/digest", response_model=CaseDigest)
async def digest(
    case_id: UUID,
    since: datetime | None = None,
    access=Depends(require_case(Permission.CASE_VIEW)),
    alert_access=Depends(require_case(Permission.ALERT_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    now = datetime.now(UTC)
    since = since or now - timedelta(days=1)
    if since.tzinfo is None or since > now:
        raise Validation("since must include a timezone and cannot be in the future")

    async def count(model, *conditions):
        return (
            await db.scalar(
                select(func.count()).select_from(model).where(model.case_id == case_id, *conditions)
            )
            or 0
        )

    alerts = list(
        await db.scalars(
            select(Alert)
            .where(Alert.case_id == case_id, Alert.status == "OPEN")
            .order_by(Alert.at.desc(), Alert.id)
            .limit(10)
        )
    )
    findings = list(
        await db.scalars(
            select(Finding)
            .where(Finding.case_id == case_id, Finding.at >= since, Finding.at <= now)
            .order_by(Finding.at.desc(), Finding.id)
            .limit(10)
        )
    )
    result = CaseDigest(
        case_id=case_id,
        since=since,
        as_of=now,
        new_evidence=await count(
            Evidence, Evidence.created_at >= since, Evidence.created_at <= now
        ),
        new_monitor_hits=await count(MonitorHit, MonitorHit.at >= since, MonitorHit.at <= now),
        open_alerts=await count(Alert, Alert.status == "OPEN"),
        pending_candidates=await db.scalar(
            select(func.count()).select_from(
                latest_links(case_id).where(LinkCandidate.status == "PENDING").subquery()
            )
        )
        or 0,
        top_alerts=[await alert_dto(db, a) for a in alerts],
        recent_findings=[FindingRef(id=f.id, title=f.title, kind=f.kind) for f in findings],
    )
    await record(
        db,
        actor=access[0],
        action="case.digest",
        case_id=case_id,
        detail={"since": since.isoformat(), "as_of": now.isoformat()},
    )
    return result
