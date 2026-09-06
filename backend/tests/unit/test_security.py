import base64
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from darknetra.config import Settings


def settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://localhost/test",
        jwt_signing_key_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
        field_key_b64=base64.b64encode(secrets.token_bytes(32)).decode(),
    )


def test_password_hash_does_not_accept_wrong_password():
    from darknetra.auth.passwords import hash_password, verify_password

    stored = hash_password("SYNTHETIC test credential 123")
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, "SYNTHETIC test credential 123")
    assert not verify_password(stored, "wrong password")
    assert not verify_password("bad hash", "wrong password")


def test_jwt_rejects_tampering_expiry_and_wrong_token_kind():
    from darknetra.auth.jwt import decode_access_token, make_access_token
    from darknetra.errors import Unauthenticated

    config = settings()
    user, session = uuid4(), uuid4()
    encoded = make_access_token(user, session, "INVESTIGATOR", config)
    decoded = decode_access_token(encoded, config)
    assert decoded["sub"] == str(user)
    assert decoded["sid"] == str(session)
    with pytest.raises(Unauthenticated):
        decode_access_token(encoded + "tampered", config)
    decoded["exp"] = datetime.now(UTC) - timedelta(seconds=5)
    expired = jwt.encode(decoded, config.jwt_signing_key, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        decode_access_token(expired, config)
    decoded["exp"] = datetime.now(UTC) + timedelta(seconds=50)
    decoded["typ"] = "refresh"
    wrong_kind = jwt.encode(decoded, config.jwt_signing_key, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        decode_access_token(wrong_kind, config)


def test_field_cipher_is_randomized_and_bound_to_its_column():
    from darknetra.crypto.fields import FieldCipher

    cipher = FieldCipher(settings().field_key)
    value = "SYNTHETIC authority reference"
    first = cipher.encrypt(value, "cases:authority_ref")
    second = cipher.encrypt(value, "cases:authority_ref")
    assert first != second
    assert cipher.decrypt(first, "cases:authority_ref") == value
    with pytest.raises(ValueError):
        cipher.decrypt(first, "evidence:locator")
    assert cipher.blind_index("  Synthetic.Handle ") == cipher.blind_index("synthetic.handle")


@pytest.mark.parametrize(
    "global_role,case_role,permission,allowed",
    [
        ("INVESTIGATOR", "ANALYST", "DECIDE", True),
        ("INVESTIGATOR", "VIEWER", "DECIDE", False),
        ("VIEWER", "OWNER", "DECIDE", False),
        ("VIEWER", "OWNER", "EVIDENCE_VIEW", True),
        ("INVESTIGATOR", "ANALYST", "EXPORT", False),
        ("INVESTIGATOR", "LEAD", "EXPORT", True),
        ("ADMIN", None, "ADMIN_SETTINGS", True),
        ("INVESTIGATOR", None, "EVIDENCE_VIEW", False),
    ],
)
def test_global_role_caps_case_permissions(global_role, case_role, permission, allowed):
    from darknetra.authz.permissions import Permission, permitted

    assert permitted(global_role, case_role, Permission(permission)) is allowed
