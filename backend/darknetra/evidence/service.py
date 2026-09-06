import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas import evidence as dto
from darknetra.audit.service import record
from darknetra.cases.models import Case
from darknetra.config import Settings
from darknetra.crypto.fields import FieldCipher
from darknetra.errors import Conflict, NotFound, TooLarge
from darknetra.evidence.codes import next_evidence_code
from darknetra.evidence.models import CustodyEvent, Derivative, Evidence
from darknetra.evidence.vault import LocalVault
from darknetra.ingest.dispatch import parse
from darknetra.ingest.sniff import quarantine_reason, sniff
from darknetra.ingest.zipsafe import ZipUnsafe, safe_members


async def get_evidence(session: AsyncSession, case_id: UUID, identifier: str | UUID) -> Evidence:
    try:
        condition = Evidence.id == UUID(str(identifier))
    except ValueError:
        condition = Evidence.code == str(identifier)
    evidence = await session.scalar(select(Evidence).where(Evidence.case_id == case_id, condition))
    if evidence is None:
        raise NotFound("Evidence not found")
    return evidence


async def evidence_dto(session, evidence, actor):
    derivatives = await session.scalars(
        select(Derivative)
        .where(Derivative.case_id == evidence.case_id, Derivative.evidence_id == evidence.id)
        .order_by(Derivative.version)
    )
    custody = await session.scalars(
        select(CustodyEvent)
        .where(CustodyEvent.case_id == evidence.case_id, CustodyEvent.evidence_id == evidence.id)
        .order_by(CustodyEvent.at)
    )
    parent = (
        await get_evidence(session, evidence.case_id, evidence.parent_evidence_id)
        if evidence.parent_evidence_id
        else None
    )
    return dto.Evidence(
        id=evidence.id,
        code=evidence.code,
        case_id=evidence.case_id,
        sha256=evidence.sha256,
        size_bytes=evidence.size_bytes,
        mime=evidence.mime,
        kind=evidence.kind,
        original_filename=evidence.original_filename,
        source_class=evidence.source_class,
        origin=evidence.origin,
        status=evidence.status,
        locator_display="[restricted locator]" if evidence.locator_enc else None,
        captured_at=evidence.captured_at,
        requested_by={"kind": evidence.requested_by_kind, "id": evidence.requested_by_id},
        parent={"id": parent.id, "code": parent.code} if parent else None,
        warnings=evidence.warnings,
        derivatives=[dto.DerivativeSummary.model_validate(d) for d in derivatives],
        custody=[
            dto.CustodyEvent(
                action=c.action,
                actor={"id": c.actor_id, "kind": c.actor_kind, "display": c.actor_kind},
                at=c.at,
                hash_verified=c.hash_verified,
                note=c.note,
            )
            for c in custody
        ],
        meta={
            k: v for k, v in evidence.meta.items() if k not in {"exif", "locator", "url", "headers"}
        },
    )


async def custody_event(session, evidence, actor, action, verified=None, note=None):
    session.add(
        CustodyEvent(
            case_id=evidence.case_id,
            evidence_id=evidence.id,
            actor_kind=actor.kind,
            actor_id=actor.id,
            action=action,
            hash_verified=verified,
            note=note,
        )
    )
    await session.flush()


async def get_derivative(session, case_id, evidence_id, kind):
    derivative = await session.scalar(
        select(Derivative)
        .where(
            Derivative.case_id == case_id,
            Derivative.evidence_id == evidence_id,
            Derivative.kind == kind,
        )
        .order_by(Derivative.version.desc())
        .limit(1)
    )
    if derivative is None:
        raise NotFound("Derivative not available")
    return derivative


async def get_text(
    session: AsyncSession, case_id: UUID, evidence_id: UUID, settings: Settings
) -> tuple[str, Derivative]:
    evidence = await get_evidence(session, case_id, evidence_id)
    if evidence.status in {"QUARANTINED", "FAILED", "EXPIRED"}:
        raise NotFound("Text not available")
    derivative = await get_derivative(session, case_id, evidence.id, "TEXT")
    with LocalVault(settings.vault_path).open(derivative.storage_key) as stream:
        return json.load(stream)["text"], derivative


async def get_derivative_text(session, case_id, evidence_id, derivative_id, settings):
    evidence = await get_evidence(session, case_id, evidence_id)
    if evidence.status in {"QUARANTINED", "FAILED", "EXPIRED"}:
        raise NotFound("Text not available")
    derivative = await session.scalar(
        select(Derivative).where(
            Derivative.case_id == case_id,
            Derivative.evidence_id == evidence_id,
            Derivative.id == derivative_id,
        )
    )
    if derivative is None:
        raise NotFound("Derivative not available")
    with LocalVault(settings.vault_path).open(derivative.storage_key) as stream:
        return json.load(stream)["text"]


async def ingest_upload(
    session,
    *,
    case,
    actor,
    file,
    settings,
    source_class="UPLOAD",
    note=None,
    source_family=None,
    defer_processing=False,
):
    vault = LocalVault(settings.vault_path)

    async def chunks():
        while chunk := await file.read(65536):
            yield chunk

    blob = await vault.put_stream(chunks(), max_bytes=settings.max_upload_bytes)
    try:
        data = blob.tmp_path.read_bytes()
    finally:
        blob.tmp_path.unlink(missing_ok=True)
    return await ingest_bytes(
        session,
        case=case,
        actor=actor,
        data=data,
        filename=file.filename or "upload",
        settings=settings,
        source_class=source_class,
        meta={
            **({"note": note} if note else {}),
            **({"source_family": source_family} if source_family else {}),
        },
        defer_processing=defer_processing,
    )


async def ingest_bytes(
    session,
    *,
    case,
    actor,
    data: bytes,
    filename: str,
    settings,
    source_class="UPLOAD",
    origin="UPLOAD",
    locator=None,
    parent_evidence_id=None,
    meta=None,
    requester_kind="USER",
    requester_id=None,
    defer_processing=False,
):
    if len(data) > settings.max_upload_bytes:
        raise TooLarge("Upload exceeds limit")
    # Serialize code allocation and dedupe in the same case transaction.
    locked_case = await session.scalar(select(Case).where(Case.id == case.id).with_for_update())
    if locked_case.status != "OPEN":
        raise Conflict("Case is not open")
    if parent_evidence_id:
        await get_evidence(session, case.id, parent_evidence_id)
    sha = hashlib.sha256(data).hexdigest()
    vault = LocalVault(settings.vault_path)
    previous = await session.scalar(
        select(Evidence).where(Evidence.case_id == case.id, Evidence.sha256 == sha)
    )
    if previous:
        verified = vault.exists(previous.storage_key) and vault.hash(previous.storage_key) == sha
        await custody_event(session, previous, actor, "VERIFIED", verified)
        await record(
            session,
            actor=actor,
            action="evidence.duplicate_verified",
            case_id=case.id,
            target_type="evidence",
            target_id=previous.id,
            detail={"hash_verified": verified},
        )
        if not verified:
            previous.status = "FAILED"
        return dto.EvidenceIngestResult(
            evidence=await evidence_dto(session, previous, actor),
            duplicate=True,
            warnings=[] if verified else ["INTEGRITY_MISMATCH"],
        )
    sniffed = sniff(data, filename)
    reason = quarantine_reason(sniffed, filename, source_class)
    if sniffed.kind in {"ZIP", "WARC"} and parent_evidence_id:
        reason = "NESTED_CONTAINER_REQUIRES_REVIEW"
    if sniffed.kind == "ZIP" and not reason:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                safe_members(archive, settings.max_zip_bytes)
        except (zipfile.BadZipFile, ZipUnsafe):
            reason = "UNSAFE_ARCHIVE"
    key = await vault.put_bytes(case.id, data)
    cipher = FieldCipher(settings.field_key)
    evidence = Evidence(
        case_id=case.id,
        code=await next_evidence_code(session, case.id),
        sha256=sha,
        size_bytes=len(data),
        mime=sniffed.mime,
        kind=sniffed.kind,
        original_filename=Path(filename.replace("\\", "/")).name,
        storage_key=key,
        source_class=source_class,
        origin=origin,
        status="QUARANTINED" if reason else "PROCESSING",
        locator_enc=cipher.encrypt(locator, str(case.id)) if locator else None,
        locator_bidx=cipher.blind_index(locator) if locator else None,
        requested_by_kind=requester_kind,
        requested_by_id=requester_id or actor.user_id,
        parent_evidence_id=parent_evidence_id,
        warnings=([reason] if reason else [])
        + (["EXTENSION_MISMATCH"] if sniffed.ext_mismatch else []),
        meta=meta or {},
        created_by_kind=actor.kind,
        created_by_id=actor.id,
    )
    session.add(evidence)
    await session.flush()
    await custody_event(session, evidence, actor, "INGESTED", True)
    if reason:
        await custody_event(session, evidence, actor, "QUARANTINED", note=reason)
    elif not defer_processing:
        await process_evidence(session, evidence, actor, settings, data=data)
    await record(
        session,
        actor=actor,
        action="evidence.ingest",
        case_id=case.id,
        target_type="evidence",
        target_id=evidence.id,
        result_hash=sha,
        detail={"status": evidence.status, "source_class": source_class},
    )
    return dto.EvidenceIngestResult(
        evidence=await evidence_dto(session, evidence, actor),
        duplicate=False,
        warnings=evidence.warnings,
    )


async def process_evidence(session, evidence, actor, settings, *, data=None):
    from darknetra.extract.pipeline import run_evidence
    from darknetra.rag.index import index_evidence

    await session.scalar(
        select(Evidence)
        .where(Evidence.case_id == evidence.case_id, Evidence.id == evidence.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if evidence.status == "EXPIRED":
        raise Conflict("Expired evidence cannot be reprocessed")
    if evidence.origin == "REPORT" or evidence.source_class == "REPORT":
        raise Conflict("Generated report archives cannot be reprocessed as source evidence")
    vault = LocalVault(settings.vault_path)
    if data is None:
        if vault.hash(evidence.storage_key) != evidence.sha256:
            evidence.status = "FAILED"
            await custody_event(session, evidence, actor, "VERIFIED", False)
            return
        with vault.open(evidence.storage_key) as stream:
            data = stream.read()
    if evidence.kind == "ZIP":
        case = await session.get(Case, evidence.case_id)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in safe_members(archive, settings.max_zip_bytes):
                if not member.is_dir():
                    await ingest_bytes(
                        session,
                        case=case,
                        actor=actor,
                        data=archive.read(member),
                        filename=member.filename,
                        settings=settings,
                        source_class=evidence.source_class,
                        origin="DERIVATIVE",
                        parent_evidence_id=evidence.id,
                        meta={"archive_member": member.filename},
                    )
        evidence.status = "READY"
        await custody_event(session, evidence, actor, "DERIVED")
        await record(
            session,
            actor=actor,
            action="evidence.derived",
            case_id=evidence.case_id,
            target_type="evidence",
            target_id=evidence.id,
            detail={"kind": "ZIP", "status": evidence.status},
        )
        return
    if evidence.kind == "WARC":
        from warcio.archiveiterator import ArchiveIterator

        case = await session.get(Case, evidence.case_id)
        count = 0
        for item in ArchiveIterator(io.BytesIO(data)):
            if item.rec_type != "response" or not item.http_headers:
                continue
            if "text/html" not in (item.http_headers.get_header("Content-Type") or ""):
                continue
            payload = item.content_stream().read(settings.max_upload_bytes + 1)
            if len(payload) > settings.max_upload_bytes or count >= 2000:
                evidence.warnings = evidence.warnings + ["WARC_LIMIT_REACHED"]
                break
            count += 1
            await ingest_bytes(
                session,
                case=case,
                actor=actor,
                data=payload,
                filename=f"response-{count}.html",
                settings=settings,
                source_class=evidence.source_class,
                origin="DERIVATIVE",
                parent_evidence_id=evidence.id,
                meta={"warc_record": count},
            )
        evidence.status = "READY" if count else "PARTIAL"
        await custody_event(session, evidence, actor, "DERIVED")
        await record(
            session,
            actor=actor,
            action="evidence.derived",
            case_id=evidence.case_id,
            target_type="evidence",
            target_id=evidence.id,
            detail={"kind": "WARC", "status": evidence.status, "children": count},
        )
        return
    try:
        import asyncio

        parsed, warnings = await asyncio.to_thread(
            parse, data, evidence.kind, evidence.original_filename
        )
    except Exception as exc:
        evidence.status = "QUARANTINED" if evidence.kind == "IMAGE" else "PARTIAL"
        evidence.warnings = evidence.warnings + ["PARSER_FAILED:" + type(exc).__name__]
        await custody_event(
            session,
            evidence,
            actor,
            "QUARANTINED" if evidence.status == "QUARANTINED" else "DERIVED",
            note="Parser declined content",
        )
        await record(
            session,
            actor=actor,
            action="evidence.parser_declined",
            case_id=evidence.case_id,
            target_type="evidence",
            target_id=evidence.id,
            detail={"status": evidence.status, "error_type": type(exc).__name__},
        )
        return
    evidence.warnings = list(dict.fromkeys(evidence.warnings + warnings))
    for kind, document in parsed:
        version = (
            await session.scalar(
                select(func.max(Derivative.version)).where(
                    Derivative.case_id == evidence.case_id,
                    Derivative.evidence_id == evidence.id,
                    Derivative.kind == kind,
                )
            )
            or 0
        ) + 1
        storage_key = await vault.put_bytes(
            evidence.case_id, json.dumps(document, ensure_ascii=False).encode()
        )
        session.add(
            Derivative(
                case_id=evidence.case_id,
                evidence_id=evidence.id,
                kind=kind,
                version=version,
                storage_key=storage_key,
                status="READY",
                extractor="deterministic_parser",
                extractor_version="2",
                lang_tags=[],
                script_tags=[],
                text_len=len(document["text"]) if kind == "TEXT" else None,
                meta={"contexts": document.get("contexts", [])} if kind == "TEXT" else {},
            )
        )
    evidence.status = "PARTIAL" if warnings else "READY"
    await session.flush()
    await custody_event(session, evidence, actor, "DERIVED")
    await record(
        session,
        actor=actor,
        action="evidence.derived",
        case_id=evidence.case_id,
        target_type="evidence",
        target_id=evidence.id,
        detail={"status": evidence.status, "derivative_kinds": [kind for kind, _ in parsed]},
    )
    if any(kind == "TEXT" for kind, _ in parsed):
        await index_evidence(session, evidence.case_id, evidence.id, settings)
        await run_evidence(session, evidence.case_id, evidence.id, settings)
