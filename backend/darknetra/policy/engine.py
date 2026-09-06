"""Case policy is reloaded at every invocation and capture, never model supplied."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from darknetra.agent.models import RateCounter
from darknetra.api.v1.schemas.cases import SourcePolicy
from darknetra.authz.deps import visible_case
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.cases.models import Case
from darknetra.policy.actor import refresh_actor
from darknetra.tools.contracts import ToolContext, ToolError, ToolSpec


def evaluate(
    policy: SourcePolicy,
    *,
    offline: bool,
    network: bool,
    source_class: str | None,
    tags: frozenset[str],
) -> None:
    if network and offline:
        raise ToolError("NETWORK_REQUIRED", "Network tools are disabled in offline mode")
    if source_class and source_class not in policy.allowed_source_classes:
        raise ToolError("POLICY_DENIED", "Source class is disabled by case policy")
    if "tor" in tags and not policy.tor_enabled:
        raise ToolError("POLICY_DENIED", "Tor is disabled for this case")
    if "telegram" in tags and not policy.telegram_enabled:
        raise ToolError("POLICY_DENIED", "Telegram is disabled for this case")
    if "person_lookup" in tags:
        raise ToolError(
            "POLICY_DENIED", "Person lookup requires a supported observation-bound adapter"
        )


async def check(
    ctx: ToolContext, spec: ToolSpec, args: dict[str, Any], *, consume: bool = False
) -> Case:
    async with ctx.session_factory() as session:
        ctx.actor = await refresh_actor(session, ctx.actor)
        case, role = await visible_case(session, ctx.actor, ctx.case_id)
        if not permitted(ctx.actor.global_role, role, Permission.THREAD_RUN):
            raise ToolError("POLICY_DENIED", "Actor cannot run tools in this case")
        if ctx.actor.kind == "TOKEN" and not (
            scope_permits(ctx.actor.scopes, Permission.THREAD_RUN)
            or (
                ctx.watchlist_item_id
                and scope_permits(ctx.actor.scopes, Permission.WATCHLIST_MANAGE)
            )
        ):
            raise ToolError("POLICY_DENIED", "Token scope does not permit tools")
        if case.status != "OPEN":
            raise ToolError("POLICY_DENIED", "Case is read-only")
        policy = SourcePolicy.model_validate(case.source_policy)
        from darknetra.plugins.catalog import tool_enabled

        if not await tool_enabled(session, spec, policy):
            raise ToolError("POLICY_DENIED", "Plugin disabled or manifest requires review")
        evaluate(
            policy,
            offline=ctx.settings.offline_mode,
            network=spec.requires_network,
            source_class=spec.source_class,
            tags=spec.policy_tags,
        )
        if consume and spec.rate_key:
            # Serialize the sliding-hour read and increment on the case row.
            await session.execute(select(Case.id).where(Case.id == ctx.case_id).with_for_update())
            now = datetime.now(UTC)
            total = await session.scalar(
                select(func.coalesce(func.sum(RateCounter.count), 0)).where(
                    RateCounter.case_id == ctx.case_id,
                    RateCounter.rate_key == spec.rate_key,
                    RateCounter.window_start >= now - timedelta(hours=1),
                )
            )
            limits: dict[str, int] = {
                str(key): value for key, value in policy.max_requests_per_hour.items()
            }
            limit = limits.get(spec.rate_key, 0)
            if int(total or 0) >= limit:
                raise ToolError(
                    "RATE_LIMITED", "Case source hourly limit reached", {"retry_after": 60}
                )
            session.add(
                RateCounter(case_id=ctx.case_id, rate_key=spec.rate_key, window_start=now, count=1)
            )
            await session.commit()
        return case
