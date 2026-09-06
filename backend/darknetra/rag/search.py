from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from darknetra.api.v1.schemas.search import SearchHit, SearchQuery, SearchResult
from darknetra.auth.actor import Actor
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.errors import Forbidden
from darknetra.evidence.models import Derivative, Evidence
from darknetra.rag.expand import query_expansions
from darknetra.rag.models import Chunk


def rrf(*rankings, constant=60):
    scores = {}
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, 1):
            scores[identifier] = scores.get(identifier, 0) + 1 / (constant + rank)
    return scores


async def search(
    session: AsyncSession, case_id: UUID, query: SearchQuery, actor: Actor | None = None
) -> SearchResult:
    filters = query.filters
    if filters.include_quarantined:
        if actor is None:
            raise Forbidden("Original evidence permission required")
        _, role = await visible_case(session, actor, case_id)
        if not permitted(actor.global_role, role, Permission.EVIDENCE_VIEW_ORIGINAL) or (
            actor.kind == "TOKEN"
            and not scope_permits(actor.scopes, Permission.EVIDENCE_VIEW_ORIGINAL)
        ):
            raise Forbidden("Original evidence permission required")
    expansions = query_expansions(query.query)
    search_query = " OR ".join(
        '"' + term.replace('"', " ") + '"' for term in [query.query] + expansions
    )
    tsquery = func.websearch_to_tsquery("simple", search_query)
    newest = aliased(Derivative)
    latest_text = (
        select(func.max(newest.version))
        .where(
            newest.case_id == case_id,
            newest.evidence_id == Chunk.evidence_id,
            newest.kind == "TEXT",
        )
        .correlate(Chunk)
        .scalar_subquery()
    )
    conditions = [
        Chunk.case_id == case_id,
        Evidence.case_id == case_id,
        Evidence.status.in_(
            ["READY", "PARTIAL", "QUARANTINED"]
            if filters.include_quarantined
            else ["READY", "PARTIAL"]
        ),
        Chunk.derivative_version == latest_text,
    ]
    if filters.source_class:
        conditions.append(Chunk.source_class.in_(filters.source_class))
    if filters.evidence_ids:
        conditions.append(Chunk.evidence_id.in_(filters.evidence_ids))
    if filters.lang:
        conditions.append(Chunk.lang.in_(filters.lang))
    if filters.from_:
        conditions.append(Evidence.captured_at >= filters.from_)
    if filters.to:
        conditions.append(Evidence.captured_at <= filters.to)
    score = func.ts_rank_cd(Chunk.tsv, tsquery)
    stmt = (
        select(Chunk, Evidence.code, score.label("score"))
        .join(Evidence, and_(Evidence.id == Chunk.evidence_id, Evidence.case_id == Chunk.case_id))
        .where(*conditions, Chunk.tsv.op("@@")(tsquery))
        .order_by(score.desc(), Chunk.id)
        .limit(query.k)
    )
    rows = (await session.execute(stmt)).all()
    if not rows and len(query.query.split()) <= 3:
        similarity = func.similarity(Chunk.search_text, query.query)
        stmt = (
            select(Chunk, Evidence.code, similarity.label("score"))
            .join(
                Evidence, and_(Evidence.id == Chunk.evidence_id, Evidence.case_id == Chunk.case_id)
            )
            .where(
                *conditions,
                or_(
                    Chunk.text.op("%")(query.query),
                    Chunk.search_text.ilike(
                        "%" + query.query.replace("%", "\\%").replace("_", "\\_") + "%"
                    ),
                ),
            )
            .order_by(similarity.desc(), Chunk.id)
            .limit(query.k)
        )
        rows = (await session.execute(stmt)).all()
    hits = []
    for chunk, code, value in rows:
        terms = [
            term for term in [query.query] + expansions if term.casefold() in chunk.text.casefold()
        ]
        offset = max(0, chunk.text.casefold().find(terms[0].casefold()) - 80) if terms else 0
        hits.append(
            SearchHit(
                evidence={"id": chunk.evidence_id, "code": code},
                chunk_id=chunk.id,
                span={"start": chunk.span_start, "end": chunk.span_end, "line": chunk.line_no},
                snippet=chunk.text[offset : offset + 240],
                score=float(value),
                source_class=chunk.source_class,
                lang=chunk.lang,
                kind=chunk.kind,
                matched_terms=terms,
            )
        )
    return SearchResult(
        hits=hits, mode_used="lexical", dense_available=False, expansions=expansions
    )
