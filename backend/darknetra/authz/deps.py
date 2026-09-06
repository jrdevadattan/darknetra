from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.auth.actor import Actor
from darknetra.auth.jwt import decode_access_token
from darknetra.auth.models import ApiToken, Session, User
from darknetra.auth.service import token_hash, user_actor, verify_csrf
from darknetra.authz.permissions import Permission, permitted, scope_permits
from darknetra.cases.models import Case, CaseMembership
from darknetra.db import get_session
from darknetra.errors import Forbidden, NotFound, Unauthenticated


async def current_actor(
    request: Request, db: AsyncSession = Depends(get_session, scope="function")
) -> Actor:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    bearer = request.headers.get("authorization", "")
    access = request.cookies.get("darknetra_access", "")
    if bearer:
        if access:
            raise Unauthenticated("Use one authentication method per request")
        scheme, _, token = bearer.partition(" ")
        if scheme.casefold() != "bearer" or not token.startswith("dk_"):
            raise Unauthenticated("Authentication required")
        row = await db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash(token)))
        if not row or row.revoked_at or row.expires_at <= now:
            raise Unauthenticated("Authentication required")
        user = await db.get(User, row.owner_user_id)
        if not user or not user.is_active or user.must_change_password:
            raise Unauthenticated("Authentication required")
        actor = Actor(
            "TOKEN",
            row.id,
            user.global_role,
            frozenset(row.scopes),
            user_id=user.id,
            token_case_id=row.case_id,
            display=user.display_name,
        )
        if not row.last_used_at or (now - row.last_used_at).total_seconds() >= 60:
            row.last_used_at = now
    elif access:
        claims = decode_access_token(access, request.app.state.settings)
        row = await db.get(Session, UUID(claims["sid"]))
        if not row or row.revoked_at or row.expires_at <= now or str(row.user_id) != claims["sub"]:
            raise Unauthenticated("Authentication required")
        user = await db.get(User, row.user_id)
        if not user or not user.is_active:
            raise Unauthenticated("Authentication required")
        actor = user_actor(user, row.id)
        request.state.actor = actor
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            verify_csrf(request, row.csrf_hash)
    else:
        raise Unauthenticated("Authentication required")
    request.state.actor = actor
    if actor.must_change_password and request.url.path not in {
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/auth/logout",
    }:
        raise Forbidden("Password change required", detail={"must_change_password": True})
    return actor


def require(permission: Permission):
    async def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.kind == "TOKEN" or not permitted(actor.global_role, None, permission):
            raise Forbidden("Permission denied")
        return actor

    return dependency


async def visible_case(db: AsyncSession, actor: Actor, case_id: UUID) -> tuple[Case, str | None]:
    case = await db.get(Case, case_id)
    member = await db.get(CaseMembership, (case_id, actor.user_id)) if actor.user_id else None
    if (
        not case
        or (actor.global_role != "ADMIN" and not member)
        or (
            actor.kind == "TOKEN"
            and actor.token_case_id is not None
            and actor.token_case_id != case_id
        )
    ):
        raise NotFound("Resource not found")
    return case, member.role if member else None


def require_case(permission: Permission):
    async def dependency(
        case_id: UUID,
        request: Request,
        actor: Actor = Depends(current_actor),
        db: AsyncSession = Depends(get_session, scope="function"),
    ) -> tuple[Actor, Case]:
        case, role = await visible_case(db, actor, case_id)
        request.state.case_id = case_id
        request.state.case_role = role
        if not permitted(actor.global_role, role, permission) or (
            actor.kind == "TOKEN" and not scope_permits(actor.scopes, permission)
        ):
            raise Forbidden("Permission denied")
        return actor, case

    return dependency
