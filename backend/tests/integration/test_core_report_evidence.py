"""Report archives retain their export boundary when accessed as evidence."""

import io
import zipfile
from uuid import UUID

from sqlalchemy import select

from darknetra.auth.actor import Actor
from darknetra.cases.models import Case, CaseMembership
from darknetra.evidence.models import Evidence
from darknetra.evidence.service import ingest_bytes


async def test_unredacted_report_original_requires_export_and_cannot_be_reprocessed(
    client, actor_login, app
):
    user = await actor_login()
    response = await client.post(
        "/api/v1/cases", json={"title": "SYNTHETIC report boundary", "demo": True}
    )
    case_id = UUID(response.json()["id"])
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("pack.md", "SYNTHETIC unredacted report fixture")
    async with app.state.session_factory() as db:
        case = await db.scalar(select(Case).where(Case.id == case_id))
        result = await ingest_bytes(
            db,
            case=case,
            actor=Actor("USER", user.id, global_role="INVESTIGATOR", user_id=user.id),
            data=payload.getvalue(),
            filename="SYNTHETIC-report.zip",
            settings=app.state.settings,
            source_class="REPORT",
            origin="REPORT",
            meta={"redacted": False},
            defer_processing=True,
        )
        evidence_id = result.evidence.id
        evidence = await db.scalar(
            select(Evidence).where(Evidence.case_id == case_id, Evidence.id == evidence_id)
        )
        evidence.status = "READY"
        await db.commit()
    path = f"/api/v1/cases/{case_id}/evidence/{evidence_id}"
    assert (await client.get(path + "/original")).status_code == 200
    async with app.state.session_factory() as db:
        member = await db.scalar(
            select(CaseMembership).where(
                CaseMembership.case_id == case_id, CaseMembership.user_id == user.id
            )
        )
        member.role = "ANALYST"
        await db.commit()
    assert (await client.get(path + "/original")).status_code == 403
    assert (await client.post(path + "/reprocess")).status_code == 409
