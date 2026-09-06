from dataclasses import asdict

from sqlalchemy import select

from darknetra.evidence.service import get_evidence, get_text
from darknetra.rag.chunker import chunk_text
from darknetra.rag.expand import query_expansions
from darknetra.rag.models import Chunk


async def index_evidence(session, case_id, evidence_id, settings):
    evidence = await get_evidence(session, case_id, evidence_id)
    text, derivative = await get_text(session, case_id, evidence_id, settings)
    if await session.scalar(
        select(Chunk.id)
        .where(Chunk.case_id == case_id, Chunk.derivative_id == derivative.id)
        .limit(1)
    ):
        return {"dense": False, "already_indexed": True}
    drafts = chunk_text(text)
    for draft in drafts:
        session.add(
            Chunk(
                case_id=case_id,
                evidence_id=evidence_id,
                derivative_id=derivative.id,
                derivative_version=derivative.version,
                source_class=evidence.source_class,
                search_text=draft.text + " " + " ".join(query_expansions(draft.text)),
                **asdict(draft),
            )
        )
    await session.flush()
    return {"dense": False, "chunks": len(drafts)}
