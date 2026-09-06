import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import evidence as dto
from darknetra.api.v1.schemas.common import ErrorBody, Page, Rationale, SourceClass
from darknetra.audit.service import record
from darknetra.authz.deps import require_case, visible_case
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.db import get_session
from darknetra.errors import AppError, Conflict, Forbidden, NotFound, Validation
from darknetra.evidence.models import Evidence
from darknetra.evidence.service import (
    custody_event,
    evidence_dto,
    get_derivative,
    get_evidence,
    get_text,
    ingest_upload,
    process_evidence,
)
from darknetra.evidence.vault import LocalVault

router = APIRouter(tags=["evidence"])


@router.post("/cases/{case_id}/evidence", status_code=201, response_model=dto.UploadResponse)
async def upload(
    case_id: UUID,
    request: Request,
    files: list[UploadFile] = File(...),
    source_class: SourceClass = Form("UPLOAD"),
    note: str | None = Form(None),
    source_family: str | None = Form(None, pattern=r"^SYNTHETIC_[A-Z0-9_]{1,80}$"),
    access=Depends(require_case(Permission.EVIDENCE_UPLOAD)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    if source_family and (source_class != "SYNTHETIC" or not case.demo):
        raise Validation("Source families are available only for synthetic demo evidence")
    results, errors = [], []
    for file in files:
        try:
            async with db.begin_nested():
                results.append(
                    await ingest_upload(
                        db,
                        case=case,
                        actor=actor,
                        file=file,
                        settings=request.app.state.settings,
                        source_class=source_class,
                        note=note,
                        source_family=source_family,
                        defer_processing=True,
                    )
                )
        except AppError as exc:
            if exc.status == 413:
                raise
            errors.append(
                dto.UploadItemError(
                    filename=file.filename or "upload",
                    error=ErrorBody(code=exc.code, message=exc.message),
                )
            )
        finally:
            await file.close()
    await db.commit()
    for result in results:
        if result.duplicate or result.evidence.status != "PROCESSING":
            continue

        async def work(evidence_id=result.evidence.id):
            async with request.app.state.session_factory() as session:
                try:
                    row = await get_evidence(session, case_id, evidence_id)
                    await process_evidence(session, row, actor, request.app.state.settings)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    row = await get_evidence(session, case_id, evidence_id)
                    row.status = "FAILED"
                    row.warnings = list(dict.fromkeys(row.warnings + ["PROCESSING_FAILED"]))
                    await record(
                        session,
                        actor=actor,
                        action="evidence.processing_failed",
                        case_id=case_id,
                        target_type="evidence",
                        target_id=row.id,
                    )
                    await session.commit()
                    raise
            from darknetra.monitor.events import on_evidence

            await on_evidence(request.app, case_id, evidence_id)

        await request.app.state.jobs.submit(
            "evidence.process", work, key=f"evidence:{result.evidence.id}"
        )
    return dto.UploadResponse(results=results, errors=errors)


@router.get("/cases/{case_id}/evidence", response_model=Page[dto.Evidence])
async def list_evidence(
    case_id: UUID,
    source_class: str | None = None,
    origin: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    stmt = select(Evidence).where(Evidence.case_id == case_id)
    for column, value in [
        (Evidence.source_class, source_class),
        (Evidence.origin, origin),
        (Evidence.status, status),
        (Evidence.kind, kind),
    ]:
        if value:
            stmt = stmt.where(column == value)
    if q:
        stmt = stmt.where(Evidence.original_filename.ilike("%" + q + "%"))
    if cursor:
        stmt = stmt.where(Evidence.code > cursor)
    rows = list(await db.scalars(stmt.order_by(Evidence.code).limit(limit + 1)))
    return Page(
        items=[await evidence_dto(db, row, access[0]) for row in rows[:limit]],
        next_cursor=rows[limit - 1].code if len(rows) > limit else None,
    )


@router.get("/cases/{case_id}/evidence/{eid}", response_model=dto.Evidence)
async def detail(
    case_id: UUID,
    eid: str,
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await evidence_dto(db, await get_evidence(db, case_id, eid), access[0])


@router.get(
    "/cases/{case_id}/evidence/{eid}/original",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
async def original(
    case_id: UUID,
    eid: str,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_VIEW_ORIGINAL)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    evidence = await get_evidence(db, case_id, eid)
    if evidence.source_class == "REPORT" and evidence.meta.get("redacted") is False:
        actor = access[0]
        _, role = await visible_case(db, actor, case_id)
        if not permitted(actor.global_role, role, Permission.EXPORT) or (
            actor.kind == "TOKEN" and not scope_permits(actor.scopes, Permission.EXPORT)
        ):
            raise Forbidden("Unredacted report originals require export permission")
    vault = LocalVault(request.app.state.settings.vault_path)
    if not vault.exists(evidence.storage_key):
        raise NotFound("Original unavailable")
    await custody_event(db, evidence, access[0], "VIEWED_ORIGINAL")
    await record(
        db,
        actor=access[0],
        action="evidence.original_view",
        case_id=case_id,
        target_type="evidence",
        target_id=evidence.id,
    )
    return FileResponse(
        vault.path_for(evidence.storage_key),
        filename=evidence.original_filename,
        media_type="application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@router.get(
    "/cases/{case_id}/evidence/{eid}/derivatives/{kind}",
    response_model=dto.TextDerivative
    | dto.MessagesDerivative
    | dto.RowsDerivative
    | dto.ImageMetaDerivative
    | dto.HtmlSafeDerivative,
)
async def derivative(
    case_id: UUID,
    eid: str,
    kind: str,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    evidence = await get_evidence(db, case_id, eid)
    if evidence.status in {"QUARANTINED", "FAILED", "EXPIRED"}:
        raise NotFound("Derivative unavailable")
    row = await get_derivative(db, case_id, evidence.id, kind.upper())
    with LocalVault(request.app.state.settings.vault_path).open(row.storage_key) as stream:
        return json.load(stream)


@router.get("/cases/{case_id}/evidence/{eid}/context", response_model=dto.Context)
async def context(
    case_id: UUID,
    eid: str,
    request: Request,
    start: int = Query(ge=0),
    end: int = Query(gt=0),
    pad: int = Query(200, ge=0, le=1000),
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    evidence = await get_evidence(db, case_id, eid)
    text, _ = await get_text(db, case_id, evidence.id, request.app.state.settings)
    if not start < end <= len(text) or end - start + 2 * pad > 4000:
        raise Validation("Invalid context bounds")
    return dto.Context(
        evidence={"id": evidence.id, "code": evidence.code},
        span={"start": start, "end": end},
        text=text[start:end],
        before=text[max(0, start - pad) : start],
        after=text[end : end + pad],
        line_no=text.count("\n", 0, start) + 1,
    )


@router.post("/cases/{case_id}/evidence/{eid}/verify", response_model=dto.VerifyResult)
async def verify(
    case_id: UUID,
    eid: str,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_VIEW_ORIGINAL)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    evidence = await get_evidence(db, case_id, eid)
    vault = LocalVault(request.app.state.settings.vault_path)
    verified = (
        vault.exists(evidence.storage_key) and vault.hash(evidence.storage_key) == evidence.sha256
    )
    if not verified:
        evidence.status = "FAILED"
    await custody_event(db, evidence, access[0], "VERIFIED", verified)
    await record(
        db,
        actor=access[0],
        action="evidence.verify",
        case_id=case_id,
        target_type="evidence",
        target_id=evidence.id,
        detail={"hash_verified": verified},
    )
    return dto.VerifyResult(hash_verified=verified)


@router.post("/cases/{case_id}/evidence/{eid}/release", response_model=dto.Evidence)
async def release(
    case_id: UUID,
    eid: str,
    body: Rationale,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_RELEASE_QUARANTINE)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    evidence = await get_evidence(db, case_id, eid)
    if (
        case.status != "OPEN"
        or evidence.status != "QUARANTINED"
        or evidence.kind != "IMAGE"
        or "DARK_IMAGE_REVIEW_REQUIRED" not in evidence.warnings
        or not set(evidence.warnings) <= {"DARK_IMAGE_REVIEW_REQUIRED", "EXTENSION_MISMATCH"}
    ):
        raise Conflict("Only a dark-source image awaiting review can be released")
    evidence.status = "PROCESSING"
    await process_evidence(db, evidence, actor, request.app.state.settings)
    if evidence.status in {"READY", "PARTIAL"}:
        await custody_event(db, evidence, actor, "RELEASED", note=body.rationale)
    await record(
        db,
        actor=actor,
        action="evidence.release",
        case_id=case_id,
        target_type="evidence",
        target_id=evidence.id,
        detail={"rationale": body.rationale},
    )
    return await evidence_dto(db, evidence, actor)


@router.post("/cases/{case_id}/evidence/{eid}/reprocess", response_model=dto.Evidence)
async def reprocess(
    case_id: UUID,
    eid: str,
    request: Request,
    access=Depends(require_case(Permission.EVIDENCE_UPLOAD)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    actor, case = access
    evidence = await get_evidence(db, case_id, eid)
    if case.status != "OPEN" or evidence.status in {"QUARANTINED", "EXPIRED"}:
        raise Conflict("Evidence cannot be reprocessed")
    await process_evidence(db, evidence, actor, request.app.state.settings)
    await record(
        db,
        actor=actor,
        action="evidence.reprocess",
        case_id=case_id,
        target_type="evidence",
        target_id=evidence.id,
    )
    return await evidence_dto(db, evidence, actor)
