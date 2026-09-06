from uuid import UUID

from sqlalchemy import select

from darknetra.rag.models import Chunk


class SyntheticEmbedder:
    available = True
    name = "SYNTHETIC-vector-fixture-v1"
    dim = 1024

    def embed_documents(self, texts):
        return [
            [1.0, 0.0] + [0.0] * 1022 if "fruit" in t else [0.0, 1.0] + [0.0] * 1022 for t in texts
        ]

    def embed_query(self, text):
        return [1.0, 0.0] + [0.0] * 1022


async def test_semantic_hybrid_reindex_and_case_isolation(client, actor_login, app, monkeypatch):
    from darknetra.rag import embed
    from darknetra.rag.index import index_evidence

    model = SyntheticEmbedder()
    monkeypatch.setattr(embed, "get_embedder", lambda settings=None: model)
    await actor_login()
    cases = []
    for title in ("SYNTHETIC A", "SYNTHETIC B"):
        case = (await client.post("/api/v1/cases", json={"title": title, "demo": True})).json()
        base = f"/api/v1/cases/{case['id']}"
        response = await client.post(
            base + "/evidence",
            files={
                "files": ("SYNTHETIC.html", b"<html><body>SYNTHETIC fruit harvest.</body></html>")
            },
            data={"source_class": "SYNTHETIC"},
        )
        assert response.status_code == 201, response.text
        await app.state.jobs.wait_all()
        evidence = response.json()["results"][0]["evidence"]
        cases.append((case, evidence, base))
    case, evidence, base = cases[0]
    result = (
        await client.post(base + "/search", json={"query": "orchard", "mode": "semantic"})
    ).json()
    assert result["mode_used"] == "semantic" and result["dense_available"]
    assert {hit["evidence"]["id"] for hit in result["hits"]} == {evidence["id"]}
    hybrid = (await client.post(base + "/search", json={"query": "fruit", "mode": "hybrid"})).json()
    assert hybrid["mode_used"] == "hybrid"
    assert hybrid["hits"][0]["score"] == 2 / 61
    model.name = "SYNTHETIC-vector-fixture-v2"
    mismatch = (
        await client.post(base + "/search", json={"query": "fruit", "mode": "semantic"})
    ).json()
    assert not mismatch["dense_available"] and mismatch["mode_used"] == "lexical"
    async with app.state.session_factory() as db:
        before = list(await db.scalars(select(Chunk.id).where(Chunk.case_id == UUID(case["id"]))))
        stats = await index_evidence(db, UUID(case["id"]), UUID(evidence["id"]), app.state.settings)
        await db.commit()
        after = list(await db.scalars(select(Chunk.id).where(Chunk.case_id == UUID(case["id"]))))
        assert stats["dense"] and before == after
    restored = (
        await client.post(base + "/search", json={"query": "orchard", "mode": "semantic"})
    ).json()
    assert restored["dense_available"]


async def test_failed_embedding_batch_is_atomic_and_partial_index_falls_back(
    client, actor_login, app, monkeypatch
):
    from darknetra.errors import Unavailable
    from darknetra.rag import embed

    class FailingModel(SyntheticEmbedder):
        calls = 0

        def embed_documents(self, texts):
            self.calls += 1
            if self.calls > 1:
                raise Unavailable("SYNTHETIC batch failure")
            return super().embed_documents(texts)

    model = FailingModel()
    monkeypatch.setattr(embed, "get_embedder", lambda settings=None: model)
    app.state.settings.embedding_batch_size = 1
    await actor_login()
    case = (
        await client.post("/api/v1/cases", json={"title": "SYNTHETIC atomic RAG", "demo": True})
    ).json()
    base = "/api/v1/cases/" + case["id"]
    response = await client.post(
        base + "/evidence",
        files={"files": ("SYNTHETIC.txt", "SYNTHETIC fruit.\n\nSYNTHETIC vegetable.")},
        data={"source_class": "SYNTHETIC"},
    )
    assert response.status_code == 201
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        rows = list(await db.scalars(select(Chunk).where(Chunk.case_id == UUID(case["id"]))))
        assert len(rows) == 2 and all(c.embedding is None for c in rows)
        rows[0].embedding = [1.0] + [0.0] * 1023
        rows[0].embedding_model = model.name
        await db.commit()
    partial = (
        await client.post(base + "/search", json={"query": "vegetable", "mode": "semantic"})
    ).json()
    assert partial["mode_used"] == "lexical" and not partial["dense_available"]
    assert partial["hits"]
