import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from darknetra_api.security.csrf import generate_csrf_token, hash_csrf_token, verify_csrf_token
from darknetra_api.security.tokens import (
    AccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)

TEST_SIGNING_KEY_B64 = base64.b64encode(b"k" * 32).decode("ascii")
OTHER_SIGNING_KEY_B64 = base64.b64encode(b"z" * 32).decode("ascii")


def test_access_token_contains_only_stable_session_claims() -> None:
    user_id = uuid4()
    session_id = uuid4()
    token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        signing_key_b64=TEST_SIGNING_KEY_B64,
    )

    claims = decode_access_token(token, signing_key_b64=TEST_SIGNING_KEY_B64)

    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["typ"] == "access"
    assert claims["iss"] == "darknetra"
    assert claims["aud"] == "darknetra-web"
    assert set(claims) == {"sub", "sid", "typ", "iss", "aud", "iat", "nbf", "exp", "jti"}
    assert claims["exp"] - claims["iat"] <= 900
    assert claims["nbf"] == claims["iat"]


def test_access_token_rejects_wrong_signature_issuer_audience_and_expiry() -> None:
    user_id = uuid4()
    session_id = uuid4()
    token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        signing_key_b64=TEST_SIGNING_KEY_B64,
    )
    with pytest.raises(AccessTokenError):
        decode_access_token(token, signing_key_b64=OTHER_SIGNING_KEY_B64)

    expired = create_access_token(
        user_id=user_id,
        session_id=session_id,
        signing_key_b64=TEST_SIGNING_KEY_B64,
        now=datetime.now(UTC) - timedelta(minutes=16),
    )
    with pytest.raises(AccessTokenError):
        decode_access_token(expired, signing_key_b64=TEST_SIGNING_KEY_B64)

    with pytest.raises(AccessTokenError):
        decode_access_token(
            token,
            signing_key_b64=TEST_SIGNING_KEY_B64,
            issuer="wrong-issuer",
        )
    with pytest.raises(AccessTokenError):
        decode_access_token(
            token,
            signing_key_b64=TEST_SIGNING_KEY_B64,
            audience="wrong-audience",
        )


def test_signing_key_must_decode_to_exactly_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        create_access_token(
            user_id=uuid4(),
            session_id=uuid4(),
            signing_key_b64=base64.b64encode(b"too-short").decode("ascii"),
        )


def test_refresh_tokens_are_high_entropy_and_hash_only_safe() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert first != second
    assert len(first) >= 60
    first_hash = hash_refresh_token(first)
    assert first_hash != first
    assert len(first_hash) == 64
    int(first_hash, 16)


def test_csrf_token_hash_is_session_comparable_without_storing_plaintext() -> None:
    token = generate_csrf_token()
    digest = hash_csrf_token(token)

    assert token != digest
    assert len(digest) == 64
    assert verify_csrf_token(token, digest) is True
    assert verify_csrf_token("wrong-token", digest) is False
