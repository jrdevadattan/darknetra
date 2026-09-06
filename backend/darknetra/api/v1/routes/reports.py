from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import reports as dto
from darknetra.api.v1.schemas.common import Page
from darknetra.audit.service import record
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission
from darknetra.cases.models import Case
from darknetra.db import get_session
from darknetra.errors import Conflict, Unavailable
from darknetra.evidence.service import custody_event, get_evidence
from darknetra.evidence.vault import LocalVault
from darknetra.reports import service
from darknetra.reports.models import Report

router = APIRouter(tags=["reports"])


@router.post("/cases/{case_id}/reports", response_model=dto.ReportJob, status_code=202)
async def generate(
    case_id: UUID,
    body: dto.ReportRequest,
    request: Request,
    access=Depends(require_case(Permission.REPORT_GENERATE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    row = await service.create(
        db, case=case, actor=actor, options=body, settings=request.app.state.settings
    )
    await db.commit()

    async def work():
        async with request.app.state.session_factory() as session:
            try:
                report = await service.get_report(session, case_id, row.id)
                current_case = await session.scalar(select(Case).where(Case.id == case_id))
                await service.complete(
                    session,
                    report=report,
                    case=current_case,
                    actor=actor,
                    options=body,
                    settings=request.app.state.settings,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                report = await service.get_report(session, case_id, row.id)
                if report.status in {"QUEUED", "RUNNING"}:
                    report.status, report.error = (
                        "ERROR",
                        "Report generation failed; generate a new version",
                    )
                    await record(
                        session,
                        actor=actor,
                        action="report.failed",
                        case_id=case_id,
                        target_type="report",
                        target_id=row.id,
                    )
                    await session.commit()
                raise

    job_id = await request.app.state.jobs.submit("report.generate", work, key=f"report:{row.id}")
    return dto.ReportJob(report_id=row.id, job_id=job_id)


@router.get("/cases/{case_id}/reports", response_model=Page[dto.Report])
async def list_reports(
    case_id: UUID,
    cursor: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(Report).where(Report.case_id == case_id)
    if cursor:
        query = query.where(Report.version > cursor)
    rows = list(await db.scalars(query.order_by(Report.version).limit(limit + 1)))
    return Page(
        items=[await service.report_dto(db, row) for row in rows[:limit]],
        next_cursor=str(rows[limit - 1].version) if len(rows) > limit else None,
    )


@router.get("/cases/{case_id}/reports/{rid}", response_model=dto.Report)
async def get_report(
    case_id: UUID,
    rid: UUID,
    access=Depends(require_case(Permission.CASE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await service.report_dto(db, await service.get_report(db, case_id, rid))


@router.get(
    "/cases/{case_id}/reports/{rid}/download",
    response_class=Response,
    responses={
        200: {
            "description": "Immutable report artifact or detached checksum",
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in [
                    "text/markdown",
                    "text/html",
                    "application/pdf",
                    "application/zip",
                    "text/plain",
                    "application/json",
                ]
            },
        }
    },
)
async def download(
    case_id: UUID,
    rid: UUID,
    request: Request,
    format: Literal["md", "html", "pdf", "zip", "sha256", "manifest"] = "md",
    access=Depends(require_case(Permission.REPORT_GENERATE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    row = await service.get_report(db, case_id, rid)
    await service.authorized(
        db, case_id, access[0], unredacted=not row.redaction.get("applied", True)
    )
    if row.status != "DONE" or row.evidence_id is None:
        raise Conflict("Report is not complete")
    evidence = await get_evidence(db, case_id, row.evidence_id)
    if evidence.status not in {"READY", "PARTIAL"}:
        raise Conflict("Report evidence is unavailable")
    vault = LocalVault(request.app.state.settings.vault_path)
    if not vault.exists(evidence.storage_key) or vault.hash(evidence.storage_key) != row.sha256:
        raise Unavailable("Report integrity verification failed")
    await custody_event(db, evidence, access[0], "EXPORTED", True)
    await record(
        db,
        actor=access[0],
        action="report.download",
        case_id=case_id,
        target_type="report",
        target_id=row.id,
        detail={"format": format, "redacted": row.redaction.get("applied")},
        result_hash=row.sha256,
    )
    filename = f"{access[1].code}-report-v{row.version}"
    if format == "sha256":
        await db.commit()
        return Response(
            f"{row.sha256}  {filename}.zip\n",
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{filename}.zip.sha256"'},
        )
    artifact_name = {
        "md": "pack.md",
        "html": "pack.html",
        "pdf": "pack.pdf",
        "manifest": "manifest.json",
    }.get(format)
    artifact = row.includes.get("artifacts", {}).get(artifact_name) if artifact_name else None
    key, expected = (
        (artifact["storage_key"], artifact["sha256"])
        if artifact
        else (evidence.storage_key, row.sha256)
    )
    if artifact_name and not artifact or not vault.exists(key) or vault.hash(key) != expected:
        raise Unavailable("Report artifact integrity verification failed")
    await db.commit()
    mime = {
        "md": "text/markdown",
        "html": "text/html",
        "pdf": "application/pdf",
        "zip": "application/zip",
        "manifest": "application/json",
    }[format]
    return FileResponse(
        vault.path_for(key),
        filename=filename + (".manifest.json" if format == "manifest" else "." + format),
        media_type=mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-SHA256": expected,
        },
    )
