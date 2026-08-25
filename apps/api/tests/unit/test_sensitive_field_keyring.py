import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from darknetra_api.security.encryption import (
    EncryptedValue,
    SensitiveFieldCrypto,
    UnknownKeyVersionError,
)
from darknetra_api.security.keyring import (
    SensitiveFieldKeyring,
    rotate_sensitive_field,
)


def key(byte: int) -> bytes:
    return bytes([byte]) * 32


def crypto(*, active_version: str, blind_index_key: bytes | None = None) -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": key(0x11), "v2": key(0x22)},
        active_key_version=active_version,
        blind_index_key=blind_index_key or key(0x33),
    )


def test_v1_envelope_decrypts_after_v2_becomes_active() -> None:
    original = SensitiveFieldCrypto(
        field_keys={"v1": key(0x11)},
        active_key_version="v1",
        blind_index_key=key(0x33),
    ).encrypt(
        "rotation secret",
        purpose="custody.notes",
        resource_id="record-a",
    )

    keyring = SensitiveFieldKeyring(
        keys={"v1": key(0x11), "v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x33),
    )

    assert keyring.active_version == "v2"
    assert keyring.key_versions == frozenset({"v1", "v2"})
    assert (
        keyring.crypto().decrypt(
            original,
            purpose="custody.notes",
            resource_id="record-a",
        )
        == "rotation secret"
    )


def test_rotation_reencrypts_with_active_key_and_preserves_stored_blind_index() -> None:
    old_crypto = crypto(active_version="v1")
    original = old_crypto.encrypt(
        "rotation secret",
        purpose="custody.notes",
        resource_id="record-a",
    )
    stored_blind_index = old_crypto.blind_index("rotation secret", purpose="custody.notes")

    keyring = SensitiveFieldKeyring(
        keys={"v1": key(0x11), "v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x33),
    )
    result = rotate_sensitive_field(
        value=original,
        blind_index=stored_blind_index,
        purpose="custody.notes",
        resource_id="record-a",
        keyring=keyring,
    )

    assert result.value.key_version == "v2"
    assert result.value != original
    assert result.blind_index == stored_blind_index
    assert (
        keyring.crypto().decrypt(
            result.value,
            purpose="custody.notes",
            resource_id="record-a",
        )
        == "rotation secret"
    )


def test_rotation_recomputes_blind_index_only_when_explicitly_requested() -> None:
    old_crypto = crypto(active_version="v1")
    original = old_crypto.encrypt(
        "rotation secret",
        purpose="custody.notes",
        resource_id="record-a",
    )
    old_blind_index = old_crypto.blind_index("rotation secret", purpose="custody.notes")
    rotated_keyring = SensitiveFieldKeyring(
        keys={"v1": key(0x11), "v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x44),
    )

    result = rotate_sensitive_field(
        value=original,
        blind_index=old_blind_index,
        purpose="custody.notes",
        resource_id="record-a",
        keyring=rotated_keyring,
        rotate_blind_index=True,
    )

    assert result.blind_index == rotated_keyring.crypto().blind_index(
        "rotation secret", purpose="custody.notes"
    )
    assert result.blind_index != old_blind_index


def test_unknown_key_version_never_falls_back_to_active_key() -> None:
    nonce = bytes(range(12))
    ciphertext = AESGCM(key(0x22)).encrypt(
        nonce,
        b"must not decrypt",
        b"darknetra:custody.notes:record-a:v99",
    )
    unknown_version = EncryptedValue(
        key_version="v99",
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
        ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
    )

    with pytest.raises(UnknownKeyVersionError, match="unknown sensitive field key version"):
        crypto(active_version="v2").decrypt(
            unknown_version,
            purpose="custody.notes",
            resource_id="record-a",
        )
