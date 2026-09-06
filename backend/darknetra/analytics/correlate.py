"""One transaction: versioned candidates, activity, graph, and audit records."""

from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from darknetra.analytics import activity, graph
from darknetra.analytics.blocking import candidate_pairs
from darknetra.analytics.config import LinkConfig
from darknetra.analytics.inputs import load_inputs
from darknetra.analytics.link_scoring import score
from darknetra.analytics.models import ActivityCandidate, AnalyticRun, LinkCandidate
from darknetra.analytics.profiles import build_profiles
from darknetra.audit.service import digest, record
from darknetra.cases.models import Case
from darknetra.errors import Conflict, NotFound
from darknetra.evidence.service import get_text


async def score_activity(session, case_id, run_id, settings):
    evidence, observations = await load_inputs(session, case_id)
    groups = defaultdict(list)
    for obs in observations:
        groups[obs.evidence_id].append(obs)
    count = 0
    for eid in evidence:
        try:
            text, _ = await get_text(session, case_id, eid, settings)
        except (NotFound, FileNotFoundError):
            # A missing text derivative must not imply negative context was checked.
            continue
        result = activity.score_observations(text, groups[eid], eid)
        features = [f.model_dump(mode="json") for f in result.features]
        previous = await session.scalar(
            select(ActivityCandidate)
            .where(ActivityCandidate.case_id == case_id, ActivityCandidate.evidence_id == eid)
            .order_by(ActivityCandidate.version.desc())
            .limit(1)
        )
        if previous and digest(previous.features) == digest(features):
            continue
        session.add(
            ActivityCandidate(
                case_id=case_id,
                run_id=run_id,
                evidence_id=eid,
                score=result.score,
                label=result.label,
                features=features,
                status="PENDING",
                version=previous.version + 1 if previous else 1,
            )
        )
        count += 1
    return count


async def run_case(session, case_id, actor, settings, focus_entity_id=None, request_id=None):
    case = await session.scalar(select(Case).where(Case.id == case_id).with_for_update())
    if case is None:
        raise NotFound("Resource not found")
    if case.status != "OPEN":
        raise Conflict("Case is not open")
    profiles = await build_profiles(session, case_id, settings)
    indexed = {p.id: p for p in profiles}
    if focus_entity_id and focus_entity_id not in indexed:
        raise NotFound("Attributed alias not found")
    config = LinkConfig()
    pairs, truncated = candidate_pairs(profiles, config.max_pairs)
    if focus_entity_id:
        pairs = {p for p in pairs if focus_entity_id in p}
    run = AnalyticRun(
        id=uuid4(),
        case_id=case_id,
        kind="CORRELATION",
        version=config.version,
        config_digest=config.digest(),
        status="RUNNING",
        started_at=datetime.now(UTC),
        stats={},
    )
    session.add(run)
    await session.flush()
    created, rescored = 0, 0
    for a, b in sorted(pairs):
        result = score(indexed[a], indexed[b], config, corpus=profiles)
        previous = await session.scalar(
            select(LinkCandidate)
            .where(
                LinkCandidate.case_id == case_id,
                LinkCandidate.subject_a_id == a,
                LinkCandidate.subject_b_id == b,
            )
            .order_by(LinkCandidate.version.desc())
            .limit(1)
        )
        if previous and previous.feature_digest == result.feature_digest:
            continue
        session.add(
            LinkCandidate(
                case_id=case_id,
                run_id=run.id,
                subject_a_id=a,
                subject_b_id=b,
                score=result.score,
                band=result.band,
                features=[f.model_dump(mode="json") for f in result.features],
                evidence_ids=sorted(set().union(*(set(f.evidence_ids) for f in result.features))),
                contradictions=result.contradictions,
                families=result.families,
                status="PENDING",
                version=previous.version + 1 if previous else 1,
                supersedes_id=previous.id if previous else None,
                feature_digest=result.feature_digest,
                meta={**result.meta, "rescored": previous is not None},
            )
        )
        created += previous is None
        rescored += previous is not None
    activities = await score_activity(session, case_id, run.id, settings)
    await session.flush()
    graph_stats = await graph.materialise(session, case_id)
    run.stats = {
        "candidates_created": created,
        "candidates_rescored": rescored,
        "activity_versions_created": activities,
        "profiles": len(profiles),
        "pairs": len(pairs),
        "truncated": truncated,
        "warnings": ["blocking_limit_reached"] if truncated else [],
        "graph": graph_stats,
    }
    run.status, run.finished_at = "DONE", datetime.now(UTC)
    await record(
        session,
        actor=actor,
        case_id=case_id,
        action="analytics.correlate",
        target_type="analytic_run",
        target_id=run.id,
        request_id=request_id,
        detail=run.stats,
        result_hash=digest(run.stats),
    )
    return run
