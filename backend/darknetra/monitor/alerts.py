"""Audited alert creation and human lifecycle transitions."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from darknetra.agent.models import Thread
from darknetra.analytics.models import LinkCandidate
from darknetra.api.v1.schemas import alerts as dto
from darknetra.api.v1.schemas.common import EvidenceRef, FindingRef
from darknetra.api.v1.schemas.findings import FindingCreate
from darknetra.audit.service import record
from darknetra.cases.models import Case
from darknetra.cases.service import ensure_open
from darknetra.decisions.models import Decision, Finding
from darknetra.errors import Conflict, NotFound, Validation
from darknetra.evidence.models import Evidence
from darknetra.monitor.models import Alert, MonitorHit
from darknetra.monitor.triage import CONFIG_VERSION

HOURLY_CAP = 20


async def evidence_refs(db, case_id, ids):
    ids = list(dict.fromkeys(ids))
    rows = list(
        await db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case_id, Evidence.id.in_(ids))
            .order_by(Evidence.code)
        )
    )
    if len(rows) != len(ids):
        raise Validation("Alert evidence must belong to this case")
    return [EvidenceRef(id=row.id, code=row.code) for row in rows]


async def alert_dto(db, row):
    from darknetra.decisions.service import decision_dto

    decision = (
        await db.scalar(
            select(Decision).where(Decision.case_id == row.case_id, Decision.id == row.decision_id)
        )
        if row.decision_id
        else None
    )
    return dto.Alert(
        id=row.id,
        case_id=row.case_id,
        kind=row.kind,
        title=row.title,
        summary=row.summary,
        evidence=await evidence_refs(db, row.case_id, row.evidence_ids),
        item_id=row.item_id,
        diversity=row.diversity,
        config_version=row.config_version,
        status=row.status,
        finding_id=row.finding_id,
        assigned_to=row.assigned_to,
        at=row.at,
        handled_at=row.handled_at,
        decision=await decision_dto(db, decision) if decision else None,
    )


async def raise_alert(
    db,
    *,
    case_id,
    actor,
    kind,
    title,
    summary,
    evidence_ids,
    item_id=None,
    diversity=None,
    config_version=CONFIG_VERSION,
):
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ensure_open(case)
    await evidence_refs(db, case_id, evidence_ids)
    now = datetime.now(UTC)
    hour = now.replace(minute=0, second=0, microsecond=0)
    total = await db.scalar(
        select(func.count())
        .select_from(Alert)
        .where(Alert.case_id == case_id, Alert.at >= hour, Alert.kind != "OVERFLOW")
    )
    if total >= HOURLY_CAP:
        row = await db.scalar(
            select(Alert)
            .where(Alert.case_id == case_id, Alert.kind == "OVERFLOW", Alert.at >= hour)
            .order_by(Alert.at)
            .limit(1)
        )
        if row:
            row.evidence_ids = list(dict.fromkeys(row.evidence_ids + evidence_ids))
            row.diversity = {
                **row.diversity,
                "overflow_count": row.diversity.get("overflow_count", 1) + 1,
            }
            row.summary = f"{row.diversity['overflow_count']} additional review signals exceeded the case hourly alert cap."
            await record(
                db,
                actor=actor,
                action="alert.overflow_attach",
                case_id=case_id,
                target_type="alert",
                target_id=row.id,
                detail={"evidence_ids": [str(i) for i in evidence_ids]},
            )
            return row
        kind, title, summary, item_id, diversity = (
            "OVERFLOW",
            "Hourly alert overflow",
            "1 additional review signal exceeded the case hourly alert cap.",
            None,
            {"overflow_count": 1, "hour": hour.isoformat()},
        )
    row = Alert(
        case_id=case_id,
        kind=kind,
        title=title[:300],
        summary=summary,
        evidence_ids=list(dict.fromkeys(evidence_ids)),
        item_id=item_id,
        diversity=diversity or {},
        config_version=config_version,
        status="OPEN",
    )
    db.add(row)
    await db.flush()
    await record(
        db,
        actor=actor,
        action="alert.create",
        case_id=case_id,
        target_type="alert",
        target_id=row.id,
        detail={"kind": kind, "evidence_ids": [str(i) for i in evidence_ids]},
    )
    return row


async def handle(db, *, case, actor, aid, action, rationale, expected_version=None):
    from darknetra.decisions.service import create_finding, decide, finding_dto

    if not rationale.strip():
        raise Validation("A rationale is required")
    case = await db.scalar(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ensure_open(case)
    row = await db.scalar(
        select(Alert)
        .where(Alert.case_id == case.id, Alert.id == aid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        raise NotFound("Alert not found")
    if row.status != "OPEN" or expected_version not in {None, 1}:
        raise Conflict("Alert has already been handled or version is stale")
    refs = await evidence_refs(db, case.id, row.evidence_ids)
    if action == "escalate" and not refs:
        raise Conflict("An evidence-backed alert is required for escalation")
    decision = await decide(
        db,
        case=case,
        actor=actor,
        target_type="ALERT",
        target_id=aid,
        target_version=1,
        decision="REJECT" if action == "dismiss" else "ACCEPT",
        rationale=rationale,
    )
    row.decision_id = decision.id
    finding = None
    if action == "escalate":
        thread = await db.scalar(
            select(Thread)
            .where(Thread.case_id == case.id, Thread.status == "OPEN")
            .order_by(Thread.created_at)
            .limit(1)
            .with_for_update()
        )
        finding = await create_finding(
            db,
            case=case,
            actor=actor,
            data=FindingCreate(
                title=row.title,
                claim=row.summary,
                kind_hint="CANDIDATE",
                evidence_codes=[r.code for r in refs],
                method="monitor-alert-escalation",
                method_version=row.config_version,
                thread_id=thread.id if thread else None,
            ),
        )
        row.status, row.finding_id = "ESCALATED", finding.id
        if thread:
            thread.pinned_finding_ids = list(
                dict.fromkeys(thread.pinned_finding_ids + [finding.id])
            )
    await record(
        db,
        actor=actor,
        action="alert." + action,
        case_id=case.id,
        target_type="alert",
        target_id=row.id,
        detail={
            "decision_id": str(decision.id),
            "finding_id": str(finding.id) if finding else None,
        },
    )
    return await alert_dto(db, row), await finding_dto(db, finding) if finding else None


async def changes_since(db, case_id, since):
    from darknetra.decisions.service import decision_dto

    if since.tzinfo is None:
        raise Validation("since must include a timezone")
    evidence = list(
        await db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case_id, Evidence.created_at >= since)
            .order_by(Evidence.created_at)
        )
    )
    alerts = list(
        await db.scalars(
            select(Alert)
            .where(Alert.case_id == case_id, (Alert.at >= since) | (Alert.handled_at >= since))
            .order_by(Alert.at)
        )
    )
    decisions = list(
        await db.scalars(
            select(Decision)
            .where(Decision.case_id == case_id, Decision.at >= since)
            .order_by(Decision.at)
        )
    )
    findings = list(
        await db.scalars(
            select(Finding)
            .where(Finding.case_id == case_id, Finding.at >= since)
            .order_by(Finding.at)
        )
    )
    hits = await db.scalar(
        select(func.count())
        .select_from(MonitorHit)
        .where(MonitorHit.case_id == case_id, MonitorHit.at >= since)
    )
    rescored = await db.scalar(
        select(func.count())
        .select_from(LinkCandidate)
        .where(
            LinkCandidate.case_id == case_id,
            LinkCandidate.created_at >= since,
            LinkCandidate.version > 1,
        )
    )
    return dto.Changes(
        since=since,
        evidence={"count": len(evidence), "codes": [e.code for e in evidence[:10]]},
        hits=hits or 0,
        alerts=[await alert_dto(db, a) for a in alerts],
        decisions=[await decision_dto(db, d) for d in decisions],
        candidates_rescored=rescored or 0,
        findings=[FindingRef(id=f.id, title=f.title, kind=f.kind) for f in findings],
    )
