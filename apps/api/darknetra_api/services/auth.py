from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.config import get_settings
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.user import User, utc_now
from darknetra_api.security.csrf import generate_csrf_token, hash_csrf_token, verify_csrf_token
from darknetra_api.security.passwords import (
    hash_password,
    validate_password_policy,
    verify_password,
)
from darknetra_api.security.tokens import (
    REFRESH_TOKEN_LIFETIME,
    AccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from darknetra_api.services.bootstrap import normalize_username

_GENERIC_AUTH_MESSAGE = "invalid credentials or session"
_DUMMY_PASSWORD_HASH = hash_password("darknetra-process-dummy-password")
_LOGIN_WINDOW = timedelta(minutes=1)
_LOGIN_LIMIT = 120
_LOGIN_ATTEMPTS: deque = deque()


class AuthenticationError(RuntimeError):
    pass


class CsrfError(RuntimeError):
    pass


class LoginRateLimited(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthContext:
    user: User
    auth_session: AuthSession


@dataclass(frozen=True)
class IssuedSession:
    user: User
    auth_session: AuthSession
    access_token: str
    refresh_token: str
    csrf_token: str


def _audit(
    db: AsyncSession,
    *,
    actor_user_id: UUID | None,
    event_type: str,
    resource_type: str,
    resource_id: str,
    request_id: str,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            case_id=None,
            request_id=request_id,
            metadata_json={},
        )
    )


def _enforce_coarse_login_limit() -> None:
    now = utc_now()
    cutoff = now - _LOGIN_WINDOW
    while _LOGIN_ATTEMPTS and _LOGIN_ATTEMPTS[0] < cutoff:
        _LOGIN_ATTEMPTS.popleft()
    if len(_LOGIN_ATTEMPTS) >= _LOGIN_LIMIT:
        raise LoginRateLimited("login rate limit exceeded")
    _LOGIN_ATTEMPTS.append(now)


def _issue_access_token(user: User, auth_session: AuthSession) -> str:
    settings = get_settings()
    return create_access_token(
        user_id=user.id,
        session_id=auth_session.id,
        signing_key_b64=settings.require_jwt_signing_key_b64(),
    )


def _build_session(user: User) -> tuple[AuthSession, str, str]:
    now = utc_now()
    refresh_token = generate_refresh_token()
    csrf_token = generate_csrf_token()
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        csrf_token_hash=hash_csrf_token(csrf_token),
        expires_at=now + REFRESH_TOKEN_LIFETIME,
        last_seen_at=now,
    )
    return auth_session, refresh_token, csrf_token


async def login(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    request_id: str,
) -> IssuedSession:
    _enforce_coarse_login_limit()
    try:
        normalized = normalize_username(username)
    except ValueError:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        _audit(
            db,
            actor_user_id=None,
            event_type="LOGIN_FAILED",
            resource_type="auth",
            resource_id="unknown",
            request_id=request_id,
        )
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE) from None

    user = await db.scalar(select(User).where(User.username_normalized == normalized).with_for_update())
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        _audit(
            db,
            actor_user_id=None,
            event_type="LOGIN_FAILED",
            resource_type="auth",
            resource_id="unknown",
            request_id=request_id,
        )
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)

    now = utc_now()
    password_matches = verify_password(password, user.password_hash)
    if not user.is_active:
        _audit(
            db,
            actor_user_id=user.id,
            event_type="LOGIN_FAILED",
            resource_type="user",
            resource_id=str(user.id),
            request_id=request_id,
        )
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)

    if user.locked_until is not None and user.locked_until > now:
        _audit(
            db,
            actor_user_id=user.id,
            event_type="LOGIN_FAILED",
            resource_type="user",
            resource_id=str(user.id),
            request_id=request_id,
        )
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    if user.locked_until is not None and user.locked_until <= now:
        user.locked_until = None
        user.failed_login_count = 0

    if not password_matches:
        user.failed_login_count += 1
        _audit(
            db,
            actor_user_id=user.id,
            event_type="LOGIN_FAILED",
            resource_type="user",
            resource_id=str(user.id),
            request_id=request_id,
        )
        if user.failed_login_count >= 5:
            user.failed_login_count = 5
            user.locked_until = now + timedelta(minutes=5)
            _audit(
                db,
                actor_user_id=user.id,
                event_type="ACCOUNT_TEMP_LOCKED",
                resource_type="user",
                resource_id=str(user.id),
                request_id=request_id,
            )
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)

    user.failed_login_count = 0
    user.locked_until = None
    auth_session, refresh_token, csrf_token = _build_session(user)
    db.add(auth_session)
    await db.flush()
    _audit(
        db,
        actor_user_id=user.id,
        event_type="LOGIN_SUCCEEDED",
        resource_type="session",
        resource_id=str(auth_session.id),
        request_id=request_id,
    )
    await db.commit()
    return IssuedSession(
        user=user,
        auth_session=auth_session,
        access_token=_issue_access_token(user, auth_session),
        refresh_token=refresh_token,
        csrf_token=csrf_token,
    )


async def get_auth_context(db: AsyncSession, *, access_token: str | None) -> AuthContext:
    if not access_token:
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    settings = get_settings()
    try:
        claims = decode_access_token(
            access_token,
            signing_key_b64=settings.require_jwt_signing_key_b64(),
        )
        user_id = UUID(str(claims["sub"]))
        session_id = UUID(str(claims["sid"]))
    except (AccessTokenError, ValueError, RuntimeError) as exc:
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE) from exc

    auth_session = await db.get(AuthSession, session_id)
    now = utc_now()
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    return AuthContext(user=user, auth_session=auth_session)


def require_csrf(auth_session: AuthSession, csrf_token: str | None) -> None:
    if not csrf_token or not verify_csrf_token(csrf_token, auth_session.csrf_token_hash):
        raise CsrfError("invalid csrf token")


async def refresh(
    db: AsyncSession,
    *,
    refresh_token: str | None,
    csrf_token: str | None,
    request_id: str,
) -> IssuedSession:
    if not refresh_token:
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    digest = hash_refresh_token(refresh_token)
    auth_session = await db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == digest).with_for_update()
    )
    if auth_session is None:
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)

    require_csrf(auth_session, csrf_token)
    now = utc_now()
    if auth_session.revoked_at is not None:
        if auth_session.revocation_reason == "rotated":
            await db.execute(
                sa.update(AuthSession)
                .where(
                    AuthSession.user_id == auth_session.user_id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now, revocation_reason="refresh_reuse_detected")
            )
            _audit(
                db,
                actor_user_id=auth_session.user_id,
                event_type="REFRESH_TOKEN_REUSE_DETECTED",
                resource_type="session",
                resource_id=str(auth_session.id),
                request_id=request_id,
            )
            await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    if auth_session.expires_at <= now:
        auth_session.revoked_at = now
        auth_session.revocation_reason = "expired"
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)

    user = await db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        auth_session.revoked_at = now
        auth_session.revocation_reason = "user_inactive"
        await db.commit()
        raise AuthenticationError(_GENERIC_AUTH_MESSAGE)

    auth_session.revoked_at = now
    auth_session.revocation_reason = "rotated"
    auth_session.last_seen_at = now
    replacement, new_refresh_token, new_csrf_token = _build_session(user)
    db.add(replacement)
    await db.flush()
    _audit(
        db,
        actor_user_id=user.id,
        event_type="SESSION_REFRESHED",
        resource_type="session",
        resource_id=str(replacement.id),
        request_id=request_id,
    )
    await db.commit()
    return IssuedSession(
        user=user,
        auth_session=replacement,
        access_token=_issue_access_token(user, replacement),
        refresh_token=new_refresh_token,
        csrf_token=new_csrf_token,
    )


async def change_password(
    db: AsyncSession,
    *,
    context: AuthContext,
    csrf_token: str | None,
    new_password: str,
    current_password: str | None,
    request_id: str,
) -> User:
    require_csrf(context.auth_session, csrf_token)
    user = context.user
    if not user.must_change_password:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise AuthenticationError(_GENERIC_AUTH_MESSAGE)
    validate_password_policy(new_password, username=user.username_normalized)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    _audit(
        db,
        actor_user_id=user.id,
        event_type="PASSWORD_CHANGED",
        resource_type="user",
        resource_id=str(user.id),
        request_id=request_id,
    )
    await db.commit()
    return user


async def logout(
    db: AsyncSession,
    *,
    context: AuthContext,
    csrf_token: str | None,
    request_id: str,
) -> None:
    require_csrf(context.auth_session, csrf_token)
    now = utc_now()
    context.auth_session.revoked_at = now
    context.auth_session.revocation_reason = "logout"
    _audit(
        db,
        actor_user_id=context.user.id,
        event_type="LOGOUT",
        resource_type="session",
        resource_id=str(context.auth_session.id),
        request_id=request_id,
    )
    await db.commit()
