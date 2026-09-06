"""Bounded provenance graphs; human confirmation is never inferred from a score."""

from collections import Counter, defaultdict
from itertools import combinations
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import aliased

from darknetra.analytics.inputs import load_inputs
from darknetra.analytics.models import GraphEdge, LinkCandidate
from darknetra.api.v1.schemas import analytics as dto
from darknetra.decisions.models import Decision
from darknetra.decisions.service import decision_dto, latest_decision
from darknetra.errors import NotFound, Validation
from darknetra.evidence.models import Evidence
from darknetra.extract.models import CanonicalEntity


def latest_links(case_id):
    newer = aliased(LinkCandidate)
    return select(LinkCandidate).where(
        LinkCandidate.case_id == case_id,
        ~exists(
            select(newer.id).where(
                newer.case_id == case_id,
                newer.subject_a_id == LinkCandidate.subject_a_id,
                newer.subject_b_id == LinkCandidate.subject_b_id,
                newer.version > LinkCandidate.version,
            )
        ),
    )


def edge_dto(row):
    return dto.GraphEdge(
        id=row.id,
        source=row.src_entity_id,
        target=row.dst_entity_id,
        type=row.type,
        status=row.status,
        score=row.score,
        families=row.families,
        candidate_id=row.candidate_id,
        decision_id=row.decision_id,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
    )


async def materialise(session, case_id):
    evidence, observations = await load_inputs(session, case_id)
    existing = {
        (e.src_entity_id, e.dst_entity_id, e.type): e
        for e in await session.scalars(select(GraphEdge).where(GraphEdge.case_id == case_id))
    }
    desired = defaultdict(set)
    by_evidence = defaultdict(set)
    authors = defaultdict(list)
    for obs in observations:
        if obs.canonical_entity_id:
            by_evidence[obs.evidence_id].add(obs.canonical_entity_id)
        if obs.canonical_entity_id and obs.meta.get("role") in {"sender", "publisher"}:
            authors[obs.evidence_id].append(obs)
    truncated = False
    for eid, ids in by_evidence.items():
        for a, b in combinations(sorted(ids), 2):
            if len(desired) >= 20000:
                truncated = True
                break
            desired[a, b, "CO_OCCURS"].add(eid)
        if truncated:
            break
    for obs in observations:
        if not obs.canonical_entity_id:
            continue
        owners = set()
        for author in authors[obs.evidence_id]:
            span = author.meta.get("context_span", {})
            if span.get("start", -1) <= obs.span_start < obs.span_end <= span.get("end", -1):
                owners.add(author.canonical_entity_id)
        if len(owners) == 1:
            owner = next(iter(owners))
            if owner != obs.canonical_entity_id:
                kind = (
                    "MENTIONS_LOCATION"
                    if obs.type == "LOCATION"
                    else "USES"
                    if obs.type
                    in {
                        "CONTACT_HANDLE",
                        "EMAIL",
                        "PHONE",
                        "BTC_ADDRESS",
                        "ETH_ADDRESS",
                        "TRON_ADDRESS",
                        "PGP_FINGERPRINT",
                    }
                    else None
                )
                if kind:
                    desired[owner, obs.canonical_entity_id, kind].add(obs.evidence_id)
    for key, ids in desired.items():
        stamps = [evidence[eid].captured_at for eid in ids]
        edge = existing.get(key)
        if edge is None:
            edge = GraphEdge(
                case_id=case_id,
                src_entity_id=key[0],
                dst_entity_id=key[1],
                type=key[2],
                status="INFO",
                families=[],
                provenance={},
                first_seen_at=min(stamps),
                last_seen_at=max(stamps),
            )
            session.add(edge)
        edge.status, edge.provenance = "INFO", {"evidence_ids": sorted(str(eid) for eid in ids)}
        edge.first_seen_at, edge.last_seen_at = min(stamps), max(stamps)
    # Obsolete derived edges are hidden; historical records remain available.
    for key, edge in existing.items():
        if edge.type in {"CO_OCCURS", "USES", "MENTIONS_LOCATION"} and key not in desired:
            edge.status = "REJECTED"
    for candidate in await session.scalars(latest_links(case_id)):
        key = (candidate.subject_a_id, candidate.subject_b_id, "POSSIBLE_SAME_OPERATOR")
        edge = existing.get(key)
        if edge is None:
            edge = GraphEdge(
                case_id=case_id,
                src_entity_id=key[0],
                dst_entity_id=key[1],
                type=key[2],
                status="PENDING",
                families=[],
                provenance={},
                first_seen_at=candidate.created_at,
                last_seen_at=candidate.created_at,
            )
            session.add(edge)
        decision = await latest_decision(session, case_id, "LINK", candidate.id, candidate.version)
        edge.status = (
            "CONFIRMED"
            if decision and decision.decision == "ACCEPT"
            else "REJECTED"
            if decision and decision.decision == "REJECT"
            else "PENDING"
        )
        edge.candidate_id, edge.decision_id = candidate.id, decision.id if decision else None
        edge.score, edge.families = candidate.score, candidate.families
        edge.provenance = {
            "evidence_ids": [str(eid) for eid in candidate.evidence_ids],
            "candidate_version": candidate.version,
        }
        edge.last_seen_at = candidate.created_at
    await session.flush()
    return {"derived_edges": len(desired), "truncated": truncated}


def virtual_edge(case_id, source, target, at):
    return dto.GraphEdge(
        id=uuid5(NAMESPACE_URL, f"darknetra:{case_id}:contains:{source}:{target}"),
        source=source,
        target=target,
        type="CONTAINS",
        status="INFO",
        score=None,
        families=[],
        first_seen_at=at,
        last_seen_at=at,
    )


async def _virtual_edges(session, case_id):
    evidence, observations = await load_inputs(session, case_id)
    edges, seen = [], set()
    for obs in observations:
        key = (obs.evidence_id, obs.canonical_entity_id)
        if obs.canonical_entity_id and key not in seen:
            edges.append(virtual_edge(case_id, *key, evidence[obs.evidence_id].captured_at))
            seen.add(key)
    for row in evidence.values():
        if row.parent_evidence_id in evidence:
            edges.append(virtual_edge(case_id, row.parent_evidence_id, row.id, row.captured_at))
    return evidence, edges


async def query(
    session,
    case_id,
    focus=None,
    depth=1,
    include_pending=True,
    include_rejected=False,
    include_evidence=False,
):
    if not 0 <= depth <= 2:
        raise Validation("Graph depth must be between zero and two")
    entities = {
        e.id: e
        for e in await session.scalars(
            select(CanonicalEntity).where(CanonicalEntity.case_id == case_id)
        )
    }
    evidence, virtual = await _virtual_edges(session, case_id) if include_evidence else ({}, [])
    if focus and focus not in entities and focus not in evidence:
        raise NotFound("Resource not found")
    latest_ids = set(
        await session.scalars(latest_links(case_id).with_only_columns(LinkCandidate.id))
    )
    stmt = select(GraphEdge).where(GraphEdge.case_id == case_id)
    if not include_pending:
        stmt = stmt.where(GraphEdge.status != "PENDING")
    if not include_rejected:
        stmt = stmt.where(GraphEdge.status != "REJECTED")
    # Confirmation on a previous candidate version does not confirm a rescore.
    stmt = stmt.where(or_(GraphEdge.candidate_id.is_(None), GraphEdge.candidate_id.in_(latest_ids)))
    raw = list(await session.scalars(stmt.order_by(GraphEdge.id)))
    edges = [edge_dto(e) for e in raw] + virtual
    available = set(entities) | set(evidence)
    edges = [e for e in edges if e.source in available and e.target in available]
    selected = {focus} if focus else set(sorted(available)[:500])
    if focus:
        frontier = {focus}
        for _ in range(depth):
            next_nodes = {
                v
                for edge in edges
                if edge.source in frontier or edge.target in frontier
                for v in (edge.source, edge.target)
            } - selected
            selected.update(next_nodes)
            frontier = next_nodes
    truncated = len(selected) > 500 or (not focus and len(available) > 500)
    # Always keep the requested focus when node truncation is needed.
    selected = set(sorted(selected - ({focus} if focus else set()))[: 499 if focus else 500]) | (
        {focus} if focus else set()
    )
    visible = [e for e in edges if e.source in selected and e.target in selected]
    truncated = truncated or len(visible) > 2000
    visible = visible[:2000]
    degrees = Counter(v for edge in visible for v in (edge.source, edge.target))
    nodes = []
    for identifier in sorted(selected):
        if identifier in entities:
            entity = entities[identifier]
            nodes.append(
                dto.GraphNode(
                    id=identifier,
                    type=entity.type,
                    label=entity.display,
                    status="OBSERVED",
                    degree=degrees[identifier],
                    meta={},
                )
            )
        else:
            item = evidence[identifier]
            nodes.append(
                dto.GraphNode(
                    id=identifier,
                    type="EVIDENCE",
                    label=item.code,
                    status=item.status,
                    degree=degrees[identifier],
                    meta={"source_class": item.source_class},
                )
            )
    return dto.GraphDTO(nodes=nodes, edges=visible, truncated=truncated, focus=focus)


async def provenance(session, case_id, edge_id, actor):
    from darknetra.analytics.serialization import link_dto
    from darknetra.evidence.service import evidence_dto

    row = await session.scalar(
        select(GraphEdge).where(GraphEdge.case_id == case_id, GraphEdge.id == edge_id)
    )
    candidate, decision = None, None
    if row:
        edge = edge_dto(row)
        ids = row.provenance.get("evidence_ids", [])
        if row.candidate_id:
            candidate = await session.scalar(
                select(LinkCandidate).where(
                    LinkCandidate.case_id == case_id, LinkCandidate.id == row.candidate_id
                )
            )
        if row.decision_id:
            decision = await session.scalar(
                select(Decision).where(Decision.case_id == case_id, Decision.id == row.decision_id)
            )
    else:
        evidence, edges = await _virtual_edges(session, case_id)
        edge = next((e for e in edges if e.id == edge_id), None)
        if edge is None:
            raise NotFound("Resource not found")
        ids = [v for v in (edge.source, edge.target) if v in evidence]
    evidence_rows = list(
        await session.scalars(
            select(Evidence)
            .where(Evidence.case_id == case_id, Evidence.id.in_(ids))
            .order_by(Evidence.code)
        )
    )
    return dto.EdgeProvenance(
        edge=edge,
        evidence=[await evidence_dto(session, e, actor) for e in evidence_rows],
        candidate=await link_dto(session, candidate) if candidate else None,
        decision=await decision_dto(session, decision) if decision else None,
    )
