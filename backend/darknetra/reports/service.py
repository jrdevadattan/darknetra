"""Versioned report jobs and content-addressed immutable completed artifacts."""

import hashlib

from sqlalchemy import func, select

from darknetra.api.v1.schemas import reports as dto
from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.cases.models import Case
from darknetra.cases.service import ensure_open
from darknetra.errors import Conflict, Forbidden, NotFound, PolicyDenied
from darknetra.evidence.service import get_evidence, ingest_bytes
from darknetra.evidence.vault import LocalVault
from darknetra.reports.model import ReportModel, build, validate_options
from darknetra.reports.models import Report
from darknetra.reports.redact import redact
from darknetra.reports.render import pack


async def authorized(db, case_id, actor, *, unredacted=False):
    user = await db.scalar(select(User).where(User.id == actor.user_id)) if actor.user_id else None
    if not user or not user.is_active or user.must_change_password:
        raise Forbidden("An active report author is required")
    case, role = await visible_case(db, actor, case_id)
    permission = Permission.EXPORT if unredacted else Permission.REPORT_GENERATE
    if (
        not permitted(user.global_role, role, permission)
        or actor.kind == "TOKEN"
        and not scope_permits(actor.scopes, permission)
    ):
        raise Forbidden(
            "Unredacted reports require export permission"
            if unredacted
            else "Report generation requires permission"
        )
    return case


async def get_report(db, case_id, rid):
    row = await db.scalar(select(Report).where(Report.case_id == case_id, Report.id == rid))
    if not row:
        raise NotFound("Report not found")
    return row


async def report_dto(db, row):
    evidence = await get_evidence(db, row.case_id, row.evidence_id) if row.evidence_id else None
    user = await db.get(User, row.generated_by)
    # Internal vault keys are implementation details, not a public browsing surface.
    includes = {k: v for k, v in row.includes.items() if k != "artifacts"}
    return dto.Report(
        id=row.id,
        case_id=row.case_id,
        version=row.version,
        evidence={"id": evidence.id, "code": evidence.code} if evidence else None,
        sha256=row.sha256,
        generated_by={
            "kind": "USER",
            "id": row.generated_by,
            "display": user.display_name if user else "User",
        },
        at=row.at,
        includes=includes,
        claim_check={"claims": 0, "unverified_dropped": 0, "dropped": [], **row.claim_check},
        redaction=row.redaction,
        status=row.status,
    )


async def create(db, *, case, actor, options, settings):
    validate_options(options)
    await authorized(db, case.id, actor, unredacted=not options.redact)
    locked = await db.scalar(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ensure_open(locked)
    if "REPORT" not in locked.source_policy["allowed_source_classes"]:
        raise PolicyDenied("Report artifacts are disabled by this case source policy")
    version = (
        await db.scalar(
            select(func.coalesce(func.max(Report.version), 0)).where(Report.case_id == case.id)
        )
    ) + 1
    row = Report(
        case_id=case.id,
        version=version,
        generated_by=actor.user_id,
        status="QUEUED",
        includes={"options": options.model_dump(mode="json", by_alias=True)},
        claim_check={"claims": 0, "unverified_dropped": 0, "dropped": []},
        redaction={"applied": options.redact},
    )
    db.add(row)
    await db.flush()
    await record(
        db,
        actor=actor,
        action="report.queued",
        case_id=case.id,
        target_type="report",
        target_id=row.id,
        detail={"version": version, "redacted": options.redact},
    )
    return row


async def complete(db, *, report, case, actor, options, settings, narrative_provider=None):
    await authorized(db, case.id, actor, unredacted=not options.redact)
    case = await db.scalar(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    ensure_open(case)
    if report.status not in {"QUEUED", "RUNNING"}:
        raise Conflict("Report is already finalized")
    report.status = "RUNNING"
    await db.flush()
    model = await build(
        db,
        case=case,
        report=report,
        actor=actor,
        options=options,
        settings=settings,
        narrative_provider=narrative_provider,
    )
    if options.redact:
        model = ReportModel.model_validate(redact(model.model_dump(mode="json")))
    files, zip_bytes = pack(model)
    vault = LocalVault(settings.vault_path)
    artifacts = {}
    for name, data in files.items():
        artifacts[name] = {
            "storage_key": await vault.put_bytes(case.id, data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
    result = await ingest_bytes(
        db,
        case=case,
        actor=actor,
        data=zip_bytes,
        filename=f"{case.code}-report-v{report.version}.zip",
        settings=settings,
        source_class="REPORT",
        origin="REPORT",
        requester_id=actor.user_id,
        meta={
            "report_id": str(report.id),
            "report_version": report.version,
            "synthetic": case.demo,
            "redacted": options.redact,
        },
        defer_processing=True,
    )
    evidence = await get_evidence(db, case.id, result.evidence.id)
    if evidence.status == "QUARANTINED":
        raise Conflict("Generated report failed archive validation")
    # A generated pack is already validated and must not recursively ingest its files.
    evidence.status = "READY"
    report.evidence_id = evidence.id
    report.storage_key_md, report.storage_key_html = (
        artifacts["pack.md"]["storage_key"],
        artifacts["pack.html"]["storage_key"],
    )
    report.sha256 = evidence.sha256
    report.includes = {
        "options": options.model_dump(mode="json", by_alias=True),
        "sections": [s.key for s in model.sections],
        "formats": ["md", "html", "pdf", "zip", "sha256", "manifest"],
        "artifacts": artifacts,
        "snapshot_evidence_count": len(model.evidence_manifest),
        "synthetic": case.demo,
    }
    report.claim_check = {
        "claims": len(model.claims),
        "unverified_dropped": len(model.dropped),
        "dropped": model.dropped,
    }
    report.redaction = {
        "applied": options.redact,
        "method": "deterministic-v1",
        "authority_withheld": options.redact,
    }
    report.status = "DONE"
    await db.flush()
    await record(
        db,
        actor=actor,
        action="report.generated",
        case_id=case.id,
        target_type="report",
        target_id=report.id,
        result_hash=report.sha256,
        detail={
            "version": report.version,
            "evidence_code": evidence.code,
            "redacted": options.redact,
        },
    )
    return report


async def generate(db, *, case, actor, options, settings):
    report = await create(db, case=case, actor=actor, options=options, settings=settings)
    return await complete(
        db, report=report, case=case, actor=actor, options=options, settings=settings
    )


async def recover_interrupted_reports(app):
    async with app.state.session_factory() as db:
        pending = list(
            await db.scalars(
                select(Report).where(Report.status.in_(["QUEUED", "RUNNING"])).with_for_update()
            )
        )
        for report in pending:
            report.status, report.error = (
                "ERROR",
                "Job interrupted by application restart; generate a new version",
            )
            await record(
                db,
                actor=Actor("SYSTEM", None),
                action="report.interrupted",
                case_id=report.case_id,
                target_type="report",
                target_id=report.id,
            )
        await db.commit()
    return len(pending)
