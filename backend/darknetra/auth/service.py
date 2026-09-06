import asyncio
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.cookies import set_cookies
from darknetra.auth.jwt import make_access_token
from darknetra.auth.models import Session, User
from darknetra.auth.passwords import dummy_hash, hash_password, verify_password
from darknetra.errors import Forbidden, Locked, Unauthenticated, Validation


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def user_actor(user: User, session_id: UUID | None = None) -> Actor:
    return Actor(
        "USER",
        user.id,
        user.global_role,
        session_id=session_id,
        user_id=user.id,
        display=user.display_name,
        must_change_password=user.must_change_password,
    )


async def issue_session(
    db: AsyncSession,
    user: User,
    request: Request,
    response: Response,
    rotated_from: UUID | None = None,
) -> Session:
    settings = request.app.state.settings
    refresh, csrf = secrets.token_hex(32), secrets.token_hex(32)
    entry = Session(
        id=uuid4(),
        user_id=user.id,
        refresh_hash=token_hash(refresh),
        csrf_hash=token_hash(csrf),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_ttl_seconds),
        rotated_from=rotated_from,
        user_agent=None,
        ip=None,
    )
    db.add(entry)
    await db.flush()
    set_cookies(
        response,
        settings,
        make_access_token(user.id, entry.id, user.global_role, settings),
        refresh,
        csrf,
    )
    return entry


async def login(
    db: AsyncSession, request: Request, response: Response, username: str, password: str
) -> User:
    if request.headers.get("origin") not in {None, request.app.state.settings.web_origin}:
        raise Forbidden("Origin is not permitted")
    user = await db.scalar(
        select(User).where(func.lower(User.username) == username.casefold()).with_for_update()
    )
    stored = user.password_hash if user else await asyncio.to_thread(dummy_hash)
    valid = await asyncio.to_thread(verify_password, stored, password)
    now = datetime.now(UTC)
    if user and user.locked_until and user.locked_until > now:
        await record(db, actor=user_actor(user), action="auth.login_locked")
        await db.commit()
        raise Locked(
            "Account temporarily locked",
            detail={"retry_after_seconds": max(1, int((user.locked_until - now).total_seconds()))},
        )
    if not user or not valid or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = now + timedelta(minutes=5)
        await record(db, actor=Actor("SYSTEM", None), action="auth.login_failed")
        await db.commit()  # Failed attempts must survive the error response transaction rollback.
        if user and user.locked_until and user.locked_until > now:
            raise Locked("Account temporarily locked", detail={"retry_after_seconds": 300})
        raise Unauthenticated("Invalid username or password")
    user.failed_logins, user.locked_until = 0, None
    entry = await issue_session(db, user, request, response)
    request.state.actor = user_actor(user, entry.id)
    await record(
        db,
        actor=request.state.actor,
        action="auth.login",
        target_type="session",
        target_id=entry.id,
    )
    return user


def verify_csrf(request: Request, stored_hash: str) -> None:
    cookie, header = (
        request.cookies.get("darknetra_csrf", ""),
        request.headers.get("x-csrf-token", ""),
    )
    if (
        not cookie
        or not header
        or request.headers.get("origin") != request.app.state.settings.web_origin
        or not hmac.compare_digest(cookie, header)
        or not hmac.compare_digest(token_hash(header), stored_hash)
    ):
        raise Forbidden("CSRF validation failed")


async def refresh(db: AsyncSession, request: Request, response: Response) -> User:
    value = request.cookies.get("darknetra_refresh", "")
    if not value:
        raise Unauthenticated("Authentication required")
    entry = await db.scalar(
        select(Session).where(Session.refresh_hash == token_hash(value)).with_for_update()
    )
    if not entry:
        raise Unauthenticated("Authentication required")
    verify_csrf(request, entry.csrf_hash)
    user = await db.get(User, entry.user_id)
    now = datetime.now(UTC)
    if not user or not user.is_active:
        raise Unauthenticated("Authentication required")
    if entry.revoked_at:
        await db.execute(
            update(Session)
            .where(Session.user_id == entry.user_id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await record(
            db,
            actor=user_actor(user),
            action="auth.refresh_reuse",
            target_type="session",
            target_id=entry.id,
        )
        await db.commit()
        raise Unauthenticated("Authentication required")
    if entry.expires_at <= now:
        raise Unauthenticated("Authentication required")
    entry.revoked_at = now
    replacement = await issue_session(db, user, request, response, rotated_from=entry.id)
    request.state.actor = user_actor(user, replacement.id)
    await record(
        db,
        actor=request.state.actor,
        action="auth.refresh",
        target_type="session",
        target_id=replacement.id,
    )
    return user


async def change_password(db: AsyncSession, actor: Actor, current: str, new: str) -> None:
    if actor.kind != "USER" or not actor.user_id:
        raise Forbidden("A user session is required")
    user = await db.scalar(select(User).where(User.id == actor.user_id).with_for_update())
    if not user or not await asyncio.to_thread(verify_password, user.password_hash, current):
        raise Unauthenticated("Current password is incorrect")
    if len(new) < 12 or len(new) > 1024 or new == current:
        raise Validation("Use a different password of at least 12 characters")
    user.password_hash = await asyncio.to_thread(hash_password, new)
    user.must_change_password = False
    await db.execute(
        update(Session)
        .where(
            Session.user_id == user.id, Session.id != actor.session_id, Session.revoked_at.is_(None)
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await record(
        db, actor=actor, action="auth.change_password", target_type="user", target_id=user.id
    )
