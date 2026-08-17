import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.passwords import hash_password, validate_password_policy

_BOOTSTRAP_ADVISORY_LOCK_KEY = 3390049102


class BootstrapAdminExists(RuntimeError):
    """Raised when the one-time administrator bootstrap has already been consumed."""


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not 3 <= len(normalized) <= 64:
        raise ValueError("username length must be between 3 and 64 characters")
    return normalized


async def bootstrap_admin(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
    request_id: str,
) -> User:
    normalized_username = normalize_username(username)
    clean_display_name = display_name.strip()
    if not clean_display_name or len(clean_display_name) > 200:
        raise ValueError("display name must contain between 1 and 200 characters")

    validate_password_policy(password, username=normalized_username)

    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _BOOTSTRAP_ADVISORY_LOCK_KEY},
    )

    existing_admin = await session.scalar(
        select(User.id).where(User.global_roles.contains([GlobalRole.ADMIN])).limit(1)
    )
    existing_username = await session.scalar(
        select(User.id).where(User.username_normalized == normalized_username).limit(1)
    )
    if existing_admin is not None or existing_username is not None:
        raise BootstrapAdminExists("administrator bootstrap has already been completed")

    user = User(
        username=username.strip(),
        username_normalized=normalized_username,
        display_name=clean_display_name,
        password_hash=hash_password(password),
        global_roles=[GlobalRole.ADMIN],
        is_active=True,
        must_change_password=True,
    )
    session.add(user)
    await session.flush()

    session.add(
        AuditEvent(
            actor_user_id=user.id,
            event_type="ADMIN_BOOTSTRAPPED",
            resource_type="user",
            resource_id=str(user.id),
            case_id=None,
            request_id=request_id,
            metadata_json={
                "username": normalized_username,
                "display_name": clean_display_name,
            },
        )
    )
    return user
