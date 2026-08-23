import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(hours=8)
DEFAULT_ISSUER = "darknetra"
DEFAULT_AUDIENCE = "darknetra-web"


class AccessTokenError(ValueError):
    """Raised when an access JWT cannot be trusted."""


def decode_signing_key(signing_key_b64: str) -> bytes:
    try:
        key = base64.b64decode(signing_key_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("JWT signing key must be valid base64 encoding exactly 32 bytes") from exc
    if len(key) != 32:
        raise ValueError("JWT signing key must decode to exactly 32 bytes")
    return key


def create_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    signing_key_b64: str,
    now: datetime | None = None,
    issuer: str = DEFAULT_ISSUER,
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    issued_at = now or datetime.now(UTC)
    issued_timestamp = int(issued_at.timestamp())
    expires_timestamp = int((issued_at + ACCESS_TOKEN_LIFETIME).timestamp())
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "access",
        "iss": issuer,
        "aud": audience,
        "iat": issued_timestamp,
        "nbf": issued_timestamp,
        "exp": expires_timestamp,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, decode_signing_key(signing_key_b64), algorithm="HS256")


def decode_access_token(
    token: str,
    *,
    signing_key_b64: str,
    issuer: str = DEFAULT_ISSUER,
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            decode_signing_key(signing_key_b64),
            algorithms=["HS256"],
            audience=audience,
            issuer=issuer,
            options={
                "require": ["sub", "sid", "typ", "iss", "aud", "iat", "nbf", "exp", "jti"],
                "strict_aud": True,
            },
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise AccessTokenError("invalid access token") from exc
    if claims.get("typ") != "access":
        raise AccessTokenError("invalid access token type")
    try:
        UUID(str(claims["sub"]))
        UUID(str(claims["sid"]))
        UUID(str(claims["jti"]))
    except (ValueError, TypeError) as exc:
        raise AccessTokenError("invalid access token identifiers") from exc
    return claims


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
