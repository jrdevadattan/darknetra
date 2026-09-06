"""SYNTHETIC Office upload remains immutable, readable, and case-isolated."""

import io
import zipfile


def synthetic_docx() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>SYNTHETIC OFFICE NEEDLE</w:t></w:r></w:p></w:body></w:document>',
        )
    return stream.getvalue()


async def create_case(client, title: str) -> str:
    response = await client.post("/api/v1/cases", json={"title": title, "demo": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_office_upload_original_text_retrieval_and_case_isolation(client, actor_login, app):
    await actor_login()
    case_a = await create_case(client, "SYNTHETIC Office A")
    case_b = await create_case(client, "SYNTHETIC Office B")
    original = synthetic_docx()
    response = await client.post(
        f"/api/v1/cases/{case_a}/evidence",
        files={"files": ("SYNTHETIC.docx", original)},
        data={"source_class": "SYNTHETIC"},
    )
    assert response.status_code == 201, response.text
    result = response.json()["results"][0]
    evidence = result["evidence"]
    assert evidence["kind"] == "OFFICE" and evidence["status"] == "PROCESSING"
    await app.state.jobs.wait_all()
    detail = await client.get(f"/api/v1/cases/{case_a}/evidence/{evidence['id']}")
    assert detail.status_code == 200 and detail.json()["status"] == "READY"

    stored = await client.get(f"/api/v1/cases/{case_a}/evidence/{evidence['id']}/original")
    assert stored.status_code == 200
    assert stored.content == original
    derivative = await client.get(
        f"/api/v1/cases/{case_a}/evidence/{evidence['id']}/derivatives/TEXT"
    )
    assert derivative.status_code == 200, derivative.text
    assert derivative.json()["text"] == "SYNTHETIC OFFICE NEEDLE"

    search = await client.post(
        f"/api/v1/cases/{case_a}/search", json={"query": "OFFICE NEEDLE", "mode": "lexical"}
    )
    assert search.status_code == 200, search.text
    assert any(hit["evidence"]["id"] == evidence["id"] for hit in search.json()["hits"])
    assert (
        await client.get(f"/api/v1/cases/{case_b}/evidence/{evidence['id']}")
    ).status_code == 404
    other_search = await client.post(
        f"/api/v1/cases/{case_b}/search", json={"query": "OFFICE NEEDLE", "mode": "lexical"}
    )
    assert other_search.status_code == 200
    assert other_search.json()["hits"] == []
