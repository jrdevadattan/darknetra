"""Local-only embeddings. Never download weights or execute repository model code."""

import asyncio
import hashlib
import math
import threading
from functools import lru_cache
from pathlib import Path

from darknetra.errors import Unavailable

_model_lock = threading.Lock()


def validate_vectors(values, expected: int) -> list[list[float]]:
    try:
        rows = [[float(v) for v in row] for row in values]
        if len(rows) != expected:
            raise ValueError
        for row in rows:
            if len(row) != 1024 or not all(math.isfinite(v) for v in row):
                raise ValueError
            norm = math.sqrt(sum(v * v for v in row))
            if not math.isfinite(norm) or norm <= 0:
                raise ValueError
            row[:] = [v / norm for v in row]
        return rows
    except (ValueError, TypeError, OverflowError):
        raise Unavailable("Embedding output is not a valid 1024-dimensional vector") from None


class NullEmbedder:
    name = "unavailable"
    dim = 0
    available = False

    def embed_documents(self, texts):
        raise Unavailable("Embedding model unavailable")

    def embed_query(self, text):
        raise Unavailable("Embedding model unavailable")


class LocalEmbedder:
    available = True
    dim = 1024

    def __init__(self, path: Path, name: str, batch_size: int):
        from sentence_transformers import SentenceTransformer

        digest = hashlib.sha256()
        # Weight/config content forms the identity, preventing mixed vector spaces after restart.
        for file in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(str(file.relative_to(path)).encode())
            with file.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
        self.name = name + ":" + digest.hexdigest()
        self.model = SentenceTransformer(str(path), local_files_only=True, trust_remote_code=False)
        if self.model.get_sentence_embedding_dimension() != 1024:
            raise Unavailable("Embedding dimension must match the 1024-dimensional index")
        self.batch_size = batch_size
        self.lock = threading.Lock()

    def embed_documents(self, texts):
        if not self.lock.acquire(blocking=False):
            raise Unavailable("Embedding worker is busy")
        try:
            return validate_vectors(
                self.model.encode(
                    texts,
                    batch_size=self.batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ),
                len(texts),
            )
        finally:
            self.lock.release()

    def embed_query(self, text):
        return self.embed_documents([text])[0]


@lru_cache(maxsize=2)
def _load(path: str, name: str, batch_size: int):
    return LocalEmbedder(Path(path), name, batch_size)


def get_embedder(settings=None):
    if settings is None or getattr(settings, "embedding_backend", "none") == "none":
        return NullEmbedder()
    path = settings.embedding_model_path
    if not path or not Path(path).is_dir():
        return NullEmbedder()
    if not _model_lock.acquire(blocking=False):
        return NullEmbedder()
    try:
        return _load(
            str(Path(path).resolve()), settings.embedding_model, settings.embedding_batch_size
        )
    except Exception:
        # Unavailable optional packages/weights never disable lexical retrieval or leak paths.
        return NullEmbedder()
    finally:
        _model_lock.release()


async def load_embedder(settings):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(get_embedder, settings),
            timeout=getattr(settings, "embedding_timeout_seconds", 60),
        )
    except TimeoutError:
        return NullEmbedder()


async def encode(settings, model, texts, *, query=False):
    method = model.embed_query if query else model.embed_documents
    try:
        values = await asyncio.wait_for(
            asyncio.to_thread(method, texts),
            timeout=getattr(settings, "embedding_timeout_seconds", 60),
        )
        return validate_vectors([values] if query else values, 1 if query else len(texts))
    except Exception:
        raise Unavailable(
            "Embedding inference unavailable; lexical retrieval remains available"
        ) from None
