# Plan 05 — Retrieval: chunking, embeddings, hybrid search, context, evaluation

Milestone M2 · Owner B · Depends on 02, 04.

**Goal.** Case-scoped hybrid retrieval over every text-bearing derivative and capture, multilingual by construction, returning spans that resolve to raw evidence. Lexical search must work even when the embedding model is absent.

**Architecture.** `rag/chunker` turns derivatives into chunks with spans; `rag/embed` provides an `Embedder` with a null fallback; `rag/index` writes `chunks` rows (tsvector generated from `search_text`, embedding column nullable); `rag/search` runs lexical and dense queries and fuses them. Everything filters by `case_id`.

---

## Files

```
darknetra/rag/
├── models.py         Chunk
├── chunker.py        chunk_text(TextDoc) / chunk_messages(Messages) / chunk_rows(Rows) / chunk_ocr(OcrBlocks)
├── embed.py          Embedder protocol; BGEM3Embedder; E5SmallEmbedder; NullEmbedder; get_embedder()
├── index.py          index_evidence(evidence_id) job; reindex_case(case_id, model)
├── search.py         search(session, case_id, SearchQuery) → SearchResult
├── expand.py         query_expansions(query) → variants (lexicon + transliteration)
darknetra/api/v1/routes/search.py (replace stub)
backend/scripts/reindex.py
backend/scripts/run_retrieval_eval.py
alembic/versions/0005_chunks.py
tests/unit/rag/test_chunker.py test_expand.py test_rrf.py
tests/integration/test_index_and_search.py test_isolation.py test_retrieval_eval.py
```

---

## Interfaces

### Chunks

```python
@dataclass class ChunkDraft: ordinal: int; text: str; span_start: int; span_end: int; line_no: int | None; lang: str; script: str; kind: Literal["message","paragraph","row","ocr"]
```

Rules:
- `message`: one chunk per message (`Messages`), `line_no = message idx`; messages shorter than 3 characters are still indexed (they may carry a wallet). Span = position of the message line in the flattened TextDoc.
- `paragraph`: split TextDoc on blank lines; paragraphs > 1,200 chars are windowed at sentence boundaries (`. ! ? । \n`) into ≤ 1,200-char chunks with 150-char overlap; spans are exact raw offsets.
- `row`: one chunk per row: `"col1: v1 · col2: v2 …"` capped at 1,200 chars; `line_no = row index + 1`.
- `ocr`: one chunk per OCR/transcription block with region in `meta`.
- `lang/script` from the derivative's per-line tags (plan 02).

### `search_text`

`chunks.search_text = text + " " + " ".join(expansions)` where expansions are: transliteration candidates of lexicon variants found in the chunk (plan 04), and Latin/Devanagari/Gurmukhi variants of matched terms. `tsv` is a generated column: `to_tsvector('simple', search_text)`. GIN on `tsv`, GIN `gin_trgm_ops` on `text`, HNSW `vector_cosine_ops` on `embedding` (`m=16, ef_construction=64`).

### Embedder

```python
class Embedder(Protocol):
    name: str; dim: int
    def embed_documents(self, texts: list[str]) -> list[list[float]]
    def embed_query(self, text: str) -> list[float]
class BGEM3Embedder: FlagEmbedding.BGEM3FlagModel("BAAI/bge-m3", use_fp16=False); dense only; batch 32; max_length 1024
class E5SmallEmbedder: sentence-transformers "intfloat/multilingual-e5-small" with "query: "/"passage: " prefixes; dim 384 (requires settings.embedding_dim=384 and a reindex)
class NullEmbedder: dim 0; embed_* raise NotAvailable → index job leaves embedding NULL and sets stats.dense=false
def get_embedder() -> Embedder   # cached; chooses by settings.embedding_model; falls back to NullEmbedder on import/load error with a logged warning and /health/ready "embedding: degraded"
```

Embedding runs in a thread pool (`asyncio.to_thread`) so the event loop stays responsive; batches of 32; the job records `embedded_at` and `embedding_model` per chunk.

### Index job

`index_evidence(evidence_id)`: load text-bearing derivatives (TEXT, MESSAGES→flattened, ROWS, OCR) → chunk → insert chunks (delete-and-reinsert for the same `(evidence_id, derivative_id)` only when the derivative version changed) → embed in background → emit `store.changed(chunk)`. Called by plan 02's `process_evidence`, by plan 08's capture gate, and by `scripts/reindex.py`.

### Search

```python
class SearchQuery(BaseModel):
    query: str; mode: Literal["hybrid","lexical","semantic"] = "hybrid"; k: int = 8
    filters: SearchFilters = SearchFilters()   # source_class: list, evidence_ids: list, lang: list, from_: datetime|None, to: datetime|None, include_quarantined: bool=False
class SearchHit(BaseModel):
    evidence_id: UUID; evidence_code: str; chunk_id: UUID; span: Span; line_no: int|None; snippet: str; score: float; source_class: str; lang: str; kind: str; matched_terms: list[str]
class SearchResult(BaseModel): hits: list[SearchHit]; mode_used: str; dense_available: bool; expansions: list[str]
```

SQL sketch:

```sql
WITH lex AS (
  SELECT id, ts_rank_cd(tsv, q) AS s, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS r
  FROM chunks, websearch_to_tsquery('simple', :expanded_query) q
  WHERE case_id = :case_id AND tsv @@ q AND <filters> LIMIT 40),
den AS (
  SELECT id, 1 - (embedding <=> :qvec) AS s, row_number() OVER (ORDER BY embedding <=> :qvec) AS r
  FROM chunks WHERE case_id = :case_id AND embedding IS NOT NULL AND <filters> ORDER BY embedding <=> :qvec LIMIT 40)
SELECT id, COALESCE(1.0/(60+lex.r),0) + COALESCE(1.0/(60+den.r),0) AS rrf FROM lex FULL OUTER JOIN den USING (id) ORDER BY rrf DESC LIMIT :k;
```

- `expanded_query` = the query plus `OR`-ed expansions from `expand.py` (lexicon variants and transliterations of query tokens).
- Fallback: trigram similarity (`text % :query`) when the tsquery yields nothing and the query is ≤ 3 tokens (handles misspellings like `zirkpur`).
- Snippet: 240 chars around the best-matching term (`ts_headline` for lexical; centre of chunk for dense).
- `mode=semantic` with `NullEmbedder` → 200 with `mode_used="lexical"` and `dense_available=false` (never an error).
- Quarantined evidence excluded unless `include_quarantined` and the actor has `EVIDENCE_VIEW_ORIGINAL`.

### Endpoint

`POST /cases/{id}/search` → `SearchResult` (EVIDENCE_VIEW). Also used by the `search_evidence` tool (plan 06) with identical semantics.

### Evaluation

`backend/scripts/run_retrieval_eval.py --seed-result data/synthetic/out/seed_result.json --questions backend/evals/questions.yaml` → for each question with `lane: evidence`, run hybrid search and report recall@5 over `expected_codes`; exit non-zero below 0.9. Also writes `evals/out/retrieval-<date>.json`.

---

## Tasks

- [ ] **T1 migration 0005** (`chunks` with generated tsvector, indexes) and model.
- [ ] **T2 chunker** with unit tests for windowing, overlap, exact spans (`text[span] == chunk.text` for paragraphs), messages and rows.
- [ ] **T3 embedder** with the three implementations and `get_embedder()` fallback; test the NullEmbedder path end to end.
- [ ] **T4 index job** wired into `process_evidence`; delete-and-reinsert on version change; stats.
- [ ] **T5 expand + search** with RRF and trigram fallback; unit test RRF arithmetic; integration test Hinglish/Devanagari/Gurmukhi variants of `safed maal` all hit the same chunk (scenario 9).
- [ ] **T6 isolation contract test**: two cases with identical documents; search in A never returns B (scenario 10).
- [ ] **T7 endpoint + reindex script + eval script**.

## Acceptance gate

`run_retrieval_eval.py` recall@5 ≥ 0.9 on the evidence-lane questions; isolation test green; search works with the embedding model absent.

## Handoff

Plan 06 exposes `search` as the `search_evidence` tool; plan 09 uses `index_evidence` for monitor captures.
