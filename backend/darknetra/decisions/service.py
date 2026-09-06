"""Human review transactions. A superseding decision is an insert, never an update."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from darknetra.analytics.models import ActivityCandidate, GraphEdge, LinkCandidate
from darknetra.api.v1.schemas import findings as dto
from darknetra.api.v1.schemas.common import ActorRef, EvidenceRef
from darknetra.audit.service import digest, record
from darknetra.auth.models import User
from darknetra.authz.permissions import Permission, permitted
from darknetra.cases.models import Case, CaseMembership
from darknetra.decisions.models import Decision, Finding
from darknetra.errors import Conflict, Forbidden, NotFound, Validation
from darknetra.evidence.models import Evidence


async def _authorize(session, case, actor, permission, *, human=True):
    user_id = actor.user_id or (actor.id if actor.kind == "USER" else None)
    if (human and actor.kind != "USER") or not user_id:
        raise Forbidden("A human analyst must perform this action")
    membership = await session.scalar(
        select(CaseMembership).where(
            CaseMembership.case_id == case.id, CaseMembership.user_id == user_id
        )
    )
    role = membership.role if membership else None
    if actor.global_role != "ADMIN" and membership is None:
        raise NotFound("Resource not found")
    if not permitted(actor.global_role, role, permission):
        raise Forbidden("Permission denied")
    locked = await session.scalar(select(Case).where(Case.id == case.id).with_for_update())
    if locked is None:
        raise NotFound("Resource not found")
    if locked.status != "OPEN":
        raise Conflict("Case is not open")
    return user_id, role


async def latest_decision(session, case_id, target_type, target_id, target_version=None):
    successor = aliased(Decision)
    query = select(Decision).where(
        Decision.case_id == case_id,
        Decision.target_type == target_type,
        Decision.target_id == target_id,
        ~exists(
            select(successor.id).where(
                successor.case_id == case_id, successor.supersedes_id == Decision.id
            )
        ),
    )
    if target_version is not None:
        query = query.where(Decision.target_version == target_version)
    return await session.scalar(
        query.order_by(Decision.target_version.desc(), Decision.at.desc()).limit(1)
    )


async def actor_ref(session, user_id):
    user = await session.scalar(select(User).where(User.id == user_id))
    return ActorRef(kind="USER", id=user_id, display=user.display_name if user else "Analyst")


async def decision_dto(session, row):
    successor = await session.scalar(
        select(Decision.id).where(
            Decision.case_id == row.case_id,
            Decision.supersedes_id == row.id,
            Decision.target_type == row.target_type,
            Decision.target_id == row.target_id,
            Decision.target_version == row.target_version,
        )
    )
    return dto.Decision(
        id=row.id,
        target_type=row.target_type,
        target_id=row.target_id,
        decision=row.decision,
        rationale=row.rationale,
        decided_by=await actor_ref(session, row.decided_by),
        at=row.at,
        superseded_by=successor,
    )


async def _target(session, case_id, target_type, target_id):
    from darknetra.monitor.models import Alert

    model = {
        "LINK": LinkCandidate,
        "ACTIVITY": ActivityCandidate,
        "FINDING": Finding,
        "ALERT": Alert,
    }.get(target_type)
    if model is None:
        raise Validation("Unknown decision target")
    target = await session.scalar(
        select(model).where(model.case_id == case_id, model.id == target_id).with_for_update()
    )
    if target is None:
        raise NotFound("Resource not found")
    if target_type == "LINK":
        latest = await session.scalar(
            select(LinkCandidate)
            .where(
                LinkCandidate.case_id == case_id,
                LinkCandidate.subject_a_id == target.subject_a_id,
                LinkCandidate.subject_b_id == target.subject_b_id,
            )
            .order_by(LinkCandidate.version.desc())
            .limit(1)
        )
        if latest.id != target.id:
            raise Conflict(
                "Candidate has been rescored",
                detail={"current_target_id": str(latest.id), "current_version": latest.version},
            )
    elif target_type == "ACTIVITY":
        latest = await session.scalar(
            select(ActivityCandidate)
            .where(
                ActivityCandidate.case_id == case_id,
                ActivityCandidate.evidence_id == target.evidence_id,
            )
            .order_by(ActivityCandidate.version.desc())
            .limit(1)
        )
        if latest.id != target.id:
            raise Conflict(
                "Activity has been rescored",
                detail={"current_target_id": str(latest.id), "current_version": latest.version},
            )
    elif target_type == "FINDING" and target.status == "SUPERSEDED":
        raise Conflict("Finding has been superseded")
    return target


async def _link_effects(session, candidate, decision):
    now = datetime.now(UTC)
    edges = {
        e.type: e
        for e in await session.scalars(
            select(GraphEdge).where(
                GraphEdge.case_id == candidate.case_id,
                GraphEdge.src_entity_id == candidate.subject_a_id,
                GraphEdge.dst_entity_id == candidate.subject_b_id,
                GraphEdge.type.in_(["POSSIBLE_SAME_OPERATOR", "ANALYST_CONFIRMED_RELATED"]),
            )
        )
    }
    possible = edges.get("POSSIBLE_SAME_OPERATOR")
    if possible is None:
        possible = GraphEdge(
            case_id=candidate.case_id,
            src_entity_id=candidate.subject_a_id,
            dst_entity_id=candidate.subject_b_id,
            type="POSSIBLE_SAME_OPERATOR",
            first_seen_at=now,
            last_seen_at=now,
            status="PENDING",
            families=[],
            provenance={},
        )
        session.add(possible)
    possible.status = (
        "REJECTED"
        if decision.decision == "REJECT"
        else "CONFIRMED"
        if decision.decision == "ACCEPT"
        else "PENDING"
    )
    possible.candidate_id, possible.decision_id = candidate.id, decision.id
    possible.score, possible.families = candidate.score, candidate.families
    possible.provenance = {
        "evidence_ids": [str(eid) for eid in candidate.evidence_ids],
        "candidate_version": candidate.version,
    }
    possible.last_seen_at = now
    confirmed = edges.get("ANALYST_CONFIRMED_RELATED")
    if decision.decision == "ACCEPT":
        if confirmed is None:
            confirmed = GraphEdge(
                case_id=candidate.case_id,
                src_entity_id=candidate.subject_a_id,
                dst_entity_id=candidate.subject_b_id,
                type="ANALYST_CONFIRMED_RELATED",
                first_seen_at=now,
                last_seen_at=now,
                status="CONFIRMED",
                families=[],
                provenance={},
            )
            session.add(confirmed)
        confirmed.status, confirmed.candidate_id, confirmed.decision_id = (
            "CONFIRMED",
            candidate.id,
            decision.id,
        )
        confirmed.score, confirmed.families = candidate.score, candidate.families
        confirmed.provenance, confirmed.last_seen_at = dict(possible.provenance), now
    elif confirmed is not None:
        confirmed.status, confirmed.decision_id, confirmed.last_seen_at = (
            "REJECTED",
            decision.id,
            now,
        )


async def decide(
    session,
    *,
    case,
    actor,
    target_type,
    target_id,
    decision,
    rationale,
    supersede=False,
    target_version=None,
    request_id=None,
):
    user_id, role = await _authorize(session, case, actor, Permission.DECIDE)
    rationale = rationale.strip()
    if decision not in {"ACCEPT", "REJECT", "DEFER", "REQUEST_MORE_EVIDENCE"}:
        raise Validation("Unknown decision value")
    if (
        not rationale
        or len(rationale) > 10000
        or (decision in {"ACCEPT", "REJECT"} and len(rationale) < 10)
    ):
        raise Validation("ACCEPT and REJECT require at least ten characters of rationale")
    target = await _target(session, case.id, target_type, target_id)
    version = getattr(target, "version", 1)
    if target_version is not None and target_version != version:
        raise Conflict("Target version changed", detail={"current_version": version})
    previous = await latest_decision(session, case.id, target_type, target_id, version)
    if previous:
        if not supersede:
            raise Conflict(
                "A decision already exists for this version",
                detail={
                    "existing_decision": (await decision_dto(session, previous)).model_dump(
                        mode="json"
                    )
                },
            )
        if actor.global_role != "ADMIN" and role not in {"LEAD", "OWNER"}:
            raise Forbidden("Only a case lead or owner may supersede a decision")
    row = Decision(
        id=uuid4(),
        case_id=case.id,
        target_type=target_type,
        target_id=target_id,
        target_version=version,
        decision=decision,
        rationale=rationale,
        decided_by=user_id,
        supersedes_id=previous.id if previous else None,
        at=datetime.now(UTC),
        request_id=request_id,
    )
    session.add(row)
    await session.flush()
    if target_type in {"LINK", "ACTIVITY"}:
        target.status = {
            "ACCEPT": "ACCEPTED",
            "REJECT": "REJECTED",
            "DEFER": "PENDING",
            "REQUEST_MORE_EVIDENCE": "PENDING",
        }[decision]
        if target_type == "LINK":
            if decision in {"DEFER", "REQUEST_MORE_EVIDENCE"}:
                target.meta = {**target.meta, "deferred_at": row.at.isoformat()}
            await _link_effects(session, target, row)
    elif target_type == "FINDING":
        target.decision_id = row.id
        target.kind = "CONFIRMED" if decision == "ACCEPT" else "CANDIDATE"
        if decision != "ACCEPT":
            target.status = "DRAFT"
    elif target_type == "ALERT":
        target.status = {
            "ACCEPT": "ACKNOWLEDGED",
            "REJECT": "DISMISSED",
            "DEFER": "OPEN",
            "REQUEST_MORE_EVIDENCE": "OPEN",
        }[decision]
        target.decision_id = row.id
        target.handled_at = row.at if decision in {"ACCEPT", "REJECT"} else None
        target.handled_by = user_id if target.handled_at else None
    await record(
        session,
        actor=actor,
        case_id=case.id,
        action=f"decision.{target_type.lower()}",
        target_type="decision",
        target_id=row.id,
        request_id=request_id,
        detail={
            "target_id": str(target_id),
            "target_version": version,
            "decision": decision,
            "supersedes_id": str(previous.id) if previous else None,
        },
        result_hash=digest((await decision_dto(session, row)).model_dump(mode="json")),
    )
    return row


async def get_finding(session, case_id, finding_id, *, lock=False):
    query = select(Finding).where(Finding.case_id == case_id, Finding.id == finding_id)
    row = await session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFound("Resource not found")
    return row


async def create_finding(session, *, case, actor, data, request_id=None):
    from darknetra.agent.models import Message, Thread

    user_id, _ = await _authorize(session, case, actor, Permission.FINDING_EDIT)
    kind = (data.kind_hint or "CANDIDATE").upper()
    if kind not in {"OBSERVED", "MODEL", "CANDIDATE"}:
        raise Validation("A draft cannot claim analyst confirmation")
    if not data.claim.strip() or not data.method.strip() or not data.evidence_codes:
        raise Validation("A finding requires a claim, method and cited evidence")
    evidence = list(
        await session.scalars(
            select(Evidence).where(
                Evidence.case_id == case.id,
                Evidence.code.in_(set(data.evidence_codes)),
                Evidence.status.in_(["READY", "PARTIAL"]),
            )
        )
    )
    if len(evidence) != len(set(data.evidence_codes)):
        raise NotFound("Cited evidence not found")
    if (
        data.thread_id
        and await session.scalar(
            select(Thread.id).where(Thread.case_id == case.id, Thread.id == data.thread_id)
        )
        is None
    ):
        raise NotFound("Resource not found")
    if data.source_message_id:
        message = await session.scalar(
            select(Message).where(Message.case_id == case.id, Message.id == data.source_message_id)
        )
        if message is None or (data.thread_id and data.thread_id != message.thread_id):
            raise NotFound("Resource not found")
        if data.claim_index is None or not 0 <= data.claim_index < len(message.claims):
            raise Validation("A valid source claim index is required")
        claim = message.claims[data.claim_index]
        if claim.get("text") != data.claim or set(claim.get("evidence_codes", [])) != set(
            data.evidence_codes
        ):
            raise Validation("Finding must preserve its source claim and citations")
    elif data.claim_index is not None:
        raise Validation("claim_index requires source_message_id")
    row = Finding(
        id=uuid4(),
        case_id=case.id,
        thread_id=data.thread_id,
        title=data.title.strip(),
        claim=data.claim.strip(),
        kind=kind,
        evidence_ids=sorted(e.id for e in evidence),
        method=data.method.strip(),
        method_version=data.method_version,
        status="DRAFT",
        version=1,
        source_message_id=data.source_message_id,
        claim_index=data.claim_index,
        created_by=user_id,
        at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    await record(
        session,
        actor=actor,
        case_id=case.id,
        action="finding.create",
        target_type="finding",
        target_id=row.id,
        request_id=request_id,
        detail={"kind": kind, "evidence_ids": [str(e) for e in row.evidence_ids]},
        result_hash=digest({"claim": row.claim, "evidence_ids": row.evidence_ids}),
    )
    return row


async def finding_dto(session, row):
    evidence = list(
        await session.scalars(
            select(Evidence)
            .where(Evidence.case_id == row.case_id, Evidence.id.in_(row.evidence_ids))
            .order_by(Evidence.code)
        )
    )
    decision = await latest_decision(session, row.case_id, "FINDING", row.id, row.version)
    return dto.Finding(
        id=row.id,
        case_id=row.case_id,
        thread_id=row.thread_id,
        title=row.title,
        claim=row.claim,
        kind=row.kind,
        evidence=[EvidenceRef(id=e.id, code=e.code) for e in evidence],
        method=row.method,
        method_version=row.method_version,
        confidence=row.confidence,
        status=row.status,
        version=row.version,
        supersedes_id=row.supersedes_id,
        created_by=await actor_ref(session, row.created_by),
        at=row.at,
        decision=await decision_dto(session, decision) if decision else None,
    )


async def promote(session, *, case, actor, finding_id, decision_id, request_id=None):
    await _authorize(session, case, actor, Permission.DECIDE)
    finding = await get_finding(session, case.id, finding_id, lock=True)
    decision = await latest_decision(session, case.id, "FINDING", finding.id, finding.version)
    if decision is None or decision.id != decision_id or decision.decision != "ACCEPT":
        raise Conflict("Promotion requires the current accepting decision for this finding version")
    if finding.status == "SUPERSEDED":
        raise Conflict("Finding has been superseded")
    finding.kind, finding.status, finding.decision_id = "CONFIRMED", "PROMOTED", decision.id
    await record(
        session,
        actor=actor,
        case_id=case.id,
        action="finding.promote",
        target_type="finding",
        target_id=finding.id,
        request_id=request_id,
        detail={"decision_id": str(decision.id), "version": finding.version},
        result_hash=digest(
            {"finding_id": finding.id, "decision_id": decision.id, "kind": "CONFIRMED"}
        ),
    )
    return finding


async def supersede_finding(session, *, case, actor, finding_id, data, request_id=None):
    await _authorize(session, case, actor, Permission.FINDING_EDIT)
    original = await get_finding(session, case.id, finding_id, lock=True)
    if original.status == "SUPERSEDED":
        raise Conflict("Finding has already been superseded")
    replacement = await create_finding(
        session, case=case, actor=actor, data=data, request_id=request_id
    )
    replacement.version, replacement.supersedes_id = original.version + 1, original.id
    original.status = "SUPERSEDED"
    await record(
        session,
        actor=actor,
        case_id=case.id,
        action="finding.supersede",
        target_type="finding",
        target_id=replacement.id,
        request_id=request_id,
        detail={"supersedes_id": str(original.id), "version": replacement.version},
        result_hash=digest(
            {
                "id": replacement.id,
                "claim": replacement.claim,
                "evidence_ids": replacement.evidence_ids,
            }
        ),
    )
    return replacement
