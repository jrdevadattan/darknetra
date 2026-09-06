"""Recover committed evidence jobs after the single API process restarts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.audit.service import digest, record
from darknetra.auth.actor import Actor
from darknetra.evidence.models import Evidence

INTERRUPTED_WARNING = "PROCESSING_INTERRUPTED"


async def recover_interrupted_evidence(
    session: AsyncSession,
    case_id: UUID,
    *,
    before: datetime | None = None,
) -> int:
    """Mark orphaned processing state as recoverable failure in the caller transaction.

    Call once per case during startup, before admitting requests or starting workers.
    ``before`` can bound recovery to rows committed before startup. Locked rows are
    left to their active worker. This function never writes the vault or changes
    originals, derivative records, or custody events; it does not commit.
    """
    query = select(Evidence).where(
        Evidence.case_id == case_id,
        Evidence.status == "PROCESSING",
    )
    if before is not None:
        query = query.where(Evidence.created_at <= before)
    pending = list(
        await session.scalars(query.order_by(Evidence.id).with_for_update(skip_locked=True))
    )
    for evidence in pending:
        evidence.status = "FAILED"
        evidence.warnings = list(dict.fromkeys([*evidence.warnings, INTERRUPTED_WARNING]))
        recovery = (
            "regenerate_report"
            if evidence.origin == "REPORT" or evidence.source_class == "REPORT"
            else "reprocess"
        )
        detail = {
            "previous_status": "PROCESSING",
            "status": "FAILED",
            "reason": "APPLICATION_RESTART",
            "recovery": recovery,
        }
        await record(
            session,
            actor=Actor("SYSTEM", None),
            action="evidence.processing_interrupted",
            case_id=case_id,
            target_type="evidence",
            target_id=evidence.id,
            detail=detail,
            result_hash=digest({"evidence_id": evidence.id, "sha256": evidence.sha256, **detail}),
        )
    return len(pending)
