"""Authorization and provenance helpers for deterministic local tool adapters."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas.common import EvidenceRef
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.cases.models import Case
from darknetra.evidence.models import Evidence
from darknetra.extract.models import Observation
from darknetra.extract.visibility import current_observations
from darknetra.tools.contracts import ToolContext, ToolError


async def authorize(ctx: ToolContext, session: AsyncSession, permission: Permission) -> Case:
    case, role = await visible_case(session, ctx.actor, ctx.case_id)
    if not permitted(ctx.actor.global_role, role, permission) or (
        ctx.actor.kind == "TOKEN" and not scope_permits(ctx.actor.scopes, permission)
    ):
        raise ToolError("POLICY_DENIED", "Actor does not have this tool's case permission")
    return case


async def observation_sources(
    session: AsyncSession,
    case_id: UUID,
    *,
    entity_ids: list[UUID] | None = None,
    address: str | None = None,
) -> list[EvidenceRef]:
    statement = current_observations(case_id).with_only_columns(Evidence)
    if entity_ids is not None:
        statement = statement.where(Observation.canonical_entity_id.in_(entity_ids))
    if address is not None:
        statement = statement.where(Observation.normalized["value"].astext == address)
    rows = (await session.scalars(statement.distinct().order_by(Evidence.code).limit(200))).all()
    return [EvidenceRef(id=row.id, code=row.code) for row in rows]
