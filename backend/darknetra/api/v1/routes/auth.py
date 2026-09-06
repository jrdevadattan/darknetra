import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.pagination import page_rows
from darknetra.api.v1.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenCreate,
    TokenCreated,
    TokenInfo,
    UserMe,
)
from darknetra.api.v1.schemas.common import Page
from darknetra.audit.service import record
from darknetra.auth import service
from darknetra.auth.actor import Actor
from darknetra.auth.cookies import clear_cookies
from darknetra.auth.models import ApiToken, Session, User
from darknetra.authz.deps import current_actor, visible_case
from darknetra.authz.permissions import TOKEN_SCOPES, permitted
from darknetra.cases.models import CaseMembership
from darknetra.db import get_session
from darknetra.errors import Forbidden, NotFound, Validation

router = APIRouter(tags=["auth"])


async def me_dto(db: AsyncSession, user: User, actor: Actor | None = None) -> UserMe:
    roles = select(CaseMembership).where(CaseMembership.user_id == user.id)
    if actor and actor.token_case_id:
        roles = roles.where(CaseMembership.case_id == actor.token_case_id)
    memberships = list((await db.scalars(roles)).all())
    return UserMe(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        global_role=user.global_role,
        must_change_password=user.must_change_password,
        case_roles={str(m.case_id): m.role for m in memberships},
        scopes=sorted(actor.scopes) if actor else [],
    )


@router.post("/auth/login", response_model=UserMe)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session, scope="function"),
):
    user = await service.login(
        db, request, response, body.username, body.password.get_secret_value()
    )
    result = await me_dto(db, user)
    await db.commit()
    return result


@router.post("/auth/refresh", response_model=UserMe)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_session, scope="function")
):
    user = await service.refresh(db, request, response)
    result = await me_dto(db, user)
    await db.commit()
    return result


@router.get("/auth/me", response_model=UserMe)
async def me(
    actor: Actor = Depends(current_actor), db: AsyncSession = Depends(get_session, scope="function")
):
    user = await db.get(User, actor.user_id)
    return await me_dto(db, user, actor)


@router.post("/auth/logout", status_code=204)
async def logout(
    response: Response,
    actor: Actor = Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if actor.kind != "USER":
        raise Forbidden("A user session is required")
    await db.execute(
        update(Session).where(Session.id == actor.session_id).values(revoked_at=datetime.now(UTC))
    )
    clear_cookies(response)
    await record(db, actor=actor, action="auth.logout")
    await db.commit()


@router.post("/auth/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    actor: Actor = Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.change_password(
        db, actor, body.current_password.get_secret_value(), body.new_password.get_secret_value()
    )
    await db.commit()


@router.post("/auth/tokens", response_model=TokenCreated, status_code=201)
async def create_token(
    body: TokenCreate,
    actor: Actor = Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if actor.kind != "USER" or actor.global_role not in {"ADMIN", "INVESTIGATOR"}:
        raise Forbidden("Permission denied")
    if not body.scopes or any(scope not in TOKEN_SCOPES for scope in body.scopes):
        raise Validation("Unsupported token scope")
    if body.case_id:
        _, role = await visible_case(db, actor, body.case_id)
        for scope in body.scopes:
            if any(
                not permitted(actor.global_role, role, permission)
                for permission in TOKEN_SCOPES[scope]
            ):
                raise Forbidden("Cannot grant permissions you do not hold")
    token = "dk_" + secrets.token_hex(24)
    row = ApiToken(
        id=uuid4(),
        name=body.name,
        owner_user_id=actor.user_id,
        token_hash=service.token_hash(token),
        scopes=sorted(set(body.scopes)),
        case_id=body.case_id,
        expires_at=datetime.now(UTC) + timedelta(days=body.expires_in_days),
    )
    db.add(row)
    await db.flush()
    await record(
        db,
        actor=actor,
        action="auth.token_create",
        case_id=body.case_id,
        target_type="token",
        target_id=row.id,
        detail={"scopes": row.scopes},
    )
    result = TokenCreated(**TokenInfo.model_validate(row).model_dump(), token=token)
    await db.commit()
    return result


@router.get("/auth/tokens", response_model=Page[TokenInfo])
async def list_tokens(
    cursor: str | None = None,
    limit: int = 50,
    actor: Actor = Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if actor.kind != "USER":
        raise Forbidden("A user session is required")
    rows, next_cursor, total = await page_rows(
        db,
        select(ApiToken).where(
            ApiToken.owner_user_id == actor.user_id, ApiToken.revoked_at.is_(None)
        ),
        ApiToken,
        limit=limit,
        cursor=cursor,
    )
    return Page(
        items=[TokenInfo.model_validate(row) for row in rows], next_cursor=next_cursor, total=total
    )


@router.delete("/auth/tokens/{id}", status_code=204)
async def revoke_token(
    id: UUID,
    actor: Actor = Depends(current_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    if actor.kind != "USER":
        raise Forbidden("A user session is required")
    row = await db.scalar(
        select(ApiToken).where(ApiToken.id == id, ApiToken.owner_user_id == actor.user_id)
    )
    if not row:
        raise NotFound("Resource not found")
    row.revoked_at = datetime.now(UTC)
    await record(db, actor=actor, action="auth.token_revoke", target_type="token", target_id=id)
    await db.commit()
