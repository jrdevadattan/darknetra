"""Append audit events inside the transaction that changes business state."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.audit.models import AuditEvent
from darknetra.auth.actor import Actor


def digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record(
    session: AsyncSession,
    *,
    actor: Actor,
    action: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    case_id: UUID | None = None,
    thread_id: UUID | None = None,
    run_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
    result_hash: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_kind=actor.kind,
        actor_id=actor.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        case_id=case_id,
        thread_id=thread_id,
        run_id=run_id,
        detail=detail or {},
        result_hash=result_hash,
        request_id=request_id,
    )
    session.add(event)
    await session.flush()
    return event
