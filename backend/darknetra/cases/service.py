from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Integer, cast, func, select

from darknetra.api.v1.schemas import cases as dto
from darknetra.api.v1.schemas.common import ActorRef
from darknetra.audit.service import record
from darknetra.auth.models import User
from darknetra.cases.models import Case, CaseMembership
from darknetra.crypto.fields import FieldCipher
from darknetra.errors import Conflict


async def case_dto(db, case, actor):
    user = await db.get(User, case.created_by)
    membership = await db.get(CaseMembership, (case.id, actor.user_id)) if actor.user_id else None
    return dto.Case(
        id=case.id,
        code=case.code,
        title=case.title,
        status=case.status,
        scope_notes=case.scope_notes,
        authority_ref_present=case.authority_ref_enc is not None,
        source_policy=case.source_policy,
        legal_hold=case.legal_hold,
        demo=case.demo,
        created_by=ActorRef(
            kind="USER", id=case.created_by, display=user.display_name if user else "User"
        ),
        opened_at=case.opened_at,
        closed_at=case.closed_at,
        my_role=membership.role if membership else None,
    )


async def create(db, actor, body, settings):
    year = datetime.now(UTC).year
    await db.execute(select(func.pg_advisory_xact_lock(1700000000 + year)))
    highest = await db.scalar(
        select(func.max(cast(func.split_part(Case.code, "-", 3), Integer))).where(
            Case.code.like(f"CHD-{year}-%")
        )
    )
    cipher = FieldCipher(settings.field_key)
    case = Case(
        id=uuid4(),
        code=f"CHD-{year}-{(highest or 0) + 1:04d}",
        title=body.title,
        status="OPEN",
        scope_notes=body.scope_notes,
        source_policy=(body.source_policy or dto.SourcePolicy()).model_dump(),
        legal_hold=False,
        demo=body.demo,
        created_by=actor.user_id,
        authority_ref_enc=cipher.encrypt(body.authority_ref, "cases:authority_ref")
        if body.authority_ref
        else None,
        authority_ref_bidx=cipher.blind_index(body.authority_ref) if body.authority_ref else None,
    )
    db.add(case)
    await db.flush()
    db.add(
        CaseMembership(case_id=case.id, user_id=actor.user_id, role="OWNER", added_by=actor.user_id)
    )
    await record(
        db,
        actor=actor,
        action="case.create",
        case_id=case.id,
        target_type="case",
        target_id=case.id,
    )
    return case


def ensure_open(case):
    if case.status != "OPEN":
        raise Conflict("Case is read-only")


async def transition(db, case, actor, target, reason):
    transitions = {"OPEN": {"CLOSED"}, "CLOSED": {"OPEN", "ARCHIVED"}, "ARCHIVED": set()}
    locked = await db.scalar(
        select(Case)
        .where(Case.id == case.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target not in transitions[locked.status]:
        raise Conflict("Invalid case state transition")
    locked.status = target
    if target == "CLOSED":
        locked.closed_at = datetime.now(UTC)
    elif target == "OPEN":
        locked.closed_at = None
    elif target == "ARCHIVED":
        locked.archived_at = datetime.now(UTC)
    await record(
        db,
        actor=actor,
        action="case." + target.lower(),
        case_id=case.id,
        target_type="case",
        target_id=case.id,
        detail={"reason": reason},
    )
    return locked
