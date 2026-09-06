"""Refresh revocable identity state before background work uses cached authority."""

from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.auth.actor import Actor
from darknetra.auth.models import ApiToken, Session, User
from darknetra.tools.contracts import ToolError


async def refresh_actor(session: AsyncSession, actor: Actor) -> Actor:
    if actor.kind not in {"USER", "TOKEN"}:
        raise ToolError("POLICY_DENIED", "An active user authorization is required")
    user_id = actor.user_id or (actor.id if actor.kind == "USER" else None)
    user = await session.get(User, user_id) if user_id else None
    if not user or not user.is_active or user.must_change_password:
        raise ToolError("POLICY_DENIED", "User authorization is no longer active")
    current = replace(
        actor, user_id=user.id, global_role=user.global_role, must_change_password=False
    )
    now = datetime.now(UTC)
    if actor.kind == "TOKEN":
        token = await session.get(ApiToken, actor.id) if actor.id else None
        if (
            not token
            or token.owner_user_id != user.id
            or token.revoked_at
            or token.expires_at <= now
        ):
            raise ToolError("POLICY_DENIED", "Token authorization is no longer active")
        current = replace(
            current, scopes=actor.scopes & frozenset(token.scopes), token_case_id=token.case_id
        )
    elif actor.session_id:
        login = await session.get(Session, actor.session_id)
        if not login or login.user_id != user.id or login.revoked_at or login.expires_at <= now:
            raise ToolError("POLICY_DENIED", "Session authorization is no longer active")
    return current
