import base64
import json

import pytest
from darknetra_api.config import Settings
from darknetra_api.security.encryption import (
    EncryptedValue,
    SensitiveFieldConfigurationError,
    SensitiveFieldCrypto,
    UnknownKeyVersionError,
    crypto_from_settings,
)
from darknetra_api.security.keyring import SensitiveFieldKeyring


def key(byte: int) -> bytes:
    return bytes([byte]) * 32


def test_v1_envelope_remains_decryptable_after_v2_becomes_active() -> None:
    original_crypto = SensitiveFieldCrypto(
        field_keys={"v1": key(0x11)},
        active_key_version="v1",
        blind_index_key=key(0x33),
    )
    envelope = original_crypto.encrypt(
        "protected source locator",
        purpose="evidence.source_locator",
        resource_id="evidence-001",
    )

    keyring = SensitiveFieldKeyring(
        keys={"v1": key(0x11), "v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x33),
    )

    assert keyring.crypto().decrypt(
        envelope,
        purpose="evidence.source_locator",
        resource_id="evidence-001",
    ) == "protected source locator"


def test_reencrypt_uses_active_v2_and_preserves_blind_index() -> None:
    keyring = SensitiveFieldKeyring(
        keys={"v1": key(0x11), "v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x33),
    )
    legacy = SensitiveFieldCrypto(
        field_keys={"v1": key(0x11)},
        active_key_version="v1",
        blind_index_key=key(0x33),
    )
    plaintext = "normalized@example.test"
    envelope = legacy.encrypt(
        plaintext,
        purpose="contact.email",
        resource_id="contact-001",
    )
    before_index = legacy.blind_index(plaintext, purpose="contact.email")

    rotated = keyring.reencrypt(
        envelope,
        purpose="contact.email",
        resource_id="contact-001",
    )

    assert rotated.key_version == "v2"
    assert rotated != envelope
    assert keyring.crypto().decrypt(
        rotated,
        purpose="contact.email",
        resource_id="contact-001",
    ) == plaintext
    assert keyring.crypto().blind_index(plaintext, purpose="contact.email") == before_index


def test_unknown_key_version_fails_closed_without_active_key_fallback() -> None:
    keyring = SensitiveFieldKeyring(
        keys={"v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x33),
    )
    unavailable = EncryptedValue(
        key_version="v1",
        nonce_b64=base64.b64encode(bytes(12)).decode("ascii"),
        ciphertext_b64=base64.b64encode(bytes(16)).decode("ascii"),
    )

    with pytest.raises(UnknownKeyVersionError, match="v1"):
        keyring.reencrypt(
            unavailable,
            purpose="contact.email",
            resource_id="contact-001",
        )


def test_base64_mapping_builds_versioned_runtime_keyring() -> None:
    keyring = SensitiveFieldKeyring.from_base64_mapping(
        keys_b64={
            "v1": base64.b64encode(key(0x11)).decode("ascii"),
            "v2": base64.b64encode(key(0x22)).decode("ascii"),
        },
        active_version="v2",
        blind_index_key_b64=base64.b64encode(key(0x33)).decode("ascii"),
    )

    assert keyring.active_version == "v2"
    assert keyring.key_versions == frozenset({"v1", "v2"})
    assert "0x22" not in repr(keyring)


def test_empty_or_invalid_keyring_fails_closed() -> None:
    with pytest.raises(SensitiveFieldConfigurationError):
        SensitiveFieldKeyring(
            keys={},
            active_version="v1",
            blind_index_key=key(0x33),
        )
    with pytest.raises(SensitiveFieldConfigurationError):
        SensitiveFieldKeyring.from_json(
            keys_json='{"v1":"not-base64"}',
            active_version="v1",
            blind_index_key_b64=base64.b64encode(key(0x33)).decode("ascii"),
        )


def test_default_crypto_boundary_uses_active_versioned_keyring_from_settings() -> None:
    settings = Settings(
        field_keyring_b64_json=json.dumps(
            {
                "v1": base64.b64encode(key(0x11)).decode("ascii"),
                "v2": base64.b64encode(key(0x22)).decode("ascii"),
            }
        ),
        field_active_key_version="v2",
        field_blind_index_key_b64=base64.b64encode(key(0x33)).decode("ascii"),
    )

    boundary = crypto_from_settings(settings)
    encrypted = boundary.encrypt(
        "versioned setting",
        purpose="evidence.source_locator",
        resource_id="evidence-settings",
    )

    assert encrypted.key_version == "v2"
    assert boundary.key_versions == frozenset({"v1", "v2"})
