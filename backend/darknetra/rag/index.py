from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import func, select

from darknetra.errors import Unavailable
from darknetra.evidence.service import get_evidence, get_text
from darknetra.rag import embed
from darknetra.rag.chunker import chunk_text
from darknetra.rag.expand import query_expansions
from darknetra.rag.models import Chunk


async def index_evidence(session, case_id, evidence_id, settings):
    evidence = await get_evidence(session, case_id, evidence_id)
    text, derivative = await get_text(session, case_id, evidence_id, settings)
    chunks = list(
        await session.scalars(
            select(Chunk)
            .where(Chunk.case_id == case_id, Chunk.derivative_id == derivative.id)
            .order_by(Chunk.ordinal)
        )
    )
    already_indexed = bool(chunks)
    if not chunks:
        for draft in chunk_text(text):
            chunk = Chunk(
                case_id=case_id,
                evidence_id=evidence_id,
                derivative_id=derivative.id,
                derivative_version=derivative.version,
                source_class=evidence.source_class,
                search_text=draft.text + " " + " ".join(query_expansions(draft.text)),
                **asdict(draft),
            )
            session.add(chunk)
            chunks.append(chunk)
    await session.flush()
    model = await embed.load_embedder(settings)
    indexed = 0
    if model.available:
        pending = [c for c in chunks if c.embedding is None or c.embedding_model != model.name]
        size = getattr(settings, "embedding_batch_size", 32)
        try:
            async with session.begin_nested():
                for offset in range(0, len(pending), size):
                    batch = pending[offset : offset + size]
                    vectors = await embed.encode(settings, model, [c.text for c in batch])
                    for chunk, vector in zip(batch, vectors, strict=True):
                        chunk.embedding = vector
                        chunk.embedding_model = model.name
                        chunk.embedded_at = datetime.now(UTC)
                        indexed += 1
                    await session.flush()
        except Unavailable:
            indexed = 0
    await session.flush()
    matching = await session.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(
            Chunk.case_id == case_id,
            Chunk.derivative_id == derivative.id,
            Chunk.embedding.is_not(None),
            Chunk.embedding_model == model.name,
        )
    )
    dense = bool(chunks) and model.available and matching == len(chunks)
    return {
        "dense": dense,
        "chunks": len(chunks),
        "embedded": indexed,
        "already_indexed": already_indexed,
    }
