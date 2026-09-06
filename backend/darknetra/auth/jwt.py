"""Access tokens identify a persisted session; database roles remain authoritative."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from darknetra.config import Settings
from darknetra.errors import Unauthenticated


def make_access_token(user_id: UUID, session_id: UUID, role: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "role": role,
            "iat": now,
            "exp": now + timedelta(seconds=settings.access_ttl_seconds),
            "typ": "access",
            "iss": "darknetra",
            "aud": "darknetra-api",
        },
        settings.jwt_signing_key,
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_signing_key,
            algorithms=["HS256"],
            audience="darknetra-api",
            issuer="darknetra",
            options={"require": ["exp", "iat", "sub", "sid", "typ"]},
        )
        if claims["typ"] != "access":
            raise ValueError("Invalid token type")
        UUID(claims["sub"])
        UUID(claims["sid"])
        return claims
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise Unauthenticated("Authentication required") from None
