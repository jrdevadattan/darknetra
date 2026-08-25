import base64
from collections.abc import Iterator, Mapping

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


class ChangingSourceMapping(Mapping[str, bytes]):
    """Expose valid material on the first pass and invalid material on later passes."""

    def __init__(self) -> None:
        self.iterations = 0

    def __getitem__(self, version: str) -> bytes:
        if version != "v1":
            raise KeyError(version)
        return key(0x51) if self.iterations == 1 else b"short"

    def __iter__(self) -> Iterator[str]:
        self.iterations += 1
        yield "v1"

    def __len__(self) -> int:
        return 1


def test_keyring_snapshots_source_mapping_before_validation_and_storage() -> None:
    """Catches validation and storage observing different passes of a mutable mapping."""
    keyring = SensitiveFieldKeyring(
        keys=ChangingSourceMapping(),
        active_version="v1",
        blind_index_key=key(0x52),
    )

    service = keyring.crypto()
    encrypted = service.encrypt(
        "mapping snapshot secret",
        purpose="custody.notes",
        resource_id="record-a",
    )

    assert (
        service.decrypt(
            encrypted,
            purpose="custody.notes",
            resource_id="record-a",
        )
        == "mapping snapshot secret"
    )


def test_keyring_and_rotation_result_repr_redact_all_sensitive_material() -> None:
    """Catches maintenance object repr exposing keys, ciphertext, or blind indexes."""
    old_crypto = crypto(active_version="v1")
    original = old_crypto.encrypt(
        "repr secret",
        purpose="custody.notes",
        resource_id="record-a",
    )
    blind_index = old_crypto.blind_index("repr secret", purpose="custody.notes")
    keyring = SensitiveFieldKeyring(
        keys={"v1": key(0x11), "v2": key(0x22)},
        active_version="v2",
        blind_index_key=key(0x33),
    )
    result = rotate_sensitive_field(
        value=original,
        blind_index=blind_index,
        purpose="custody.notes",
        resource_id="record-a",
        keyring=keyring,
    )

    rendered = f"{keyring!r} {result!r}"
    assert repr(key(0x11)) not in rendered
    assert repr(key(0x22)) not in rendered
    assert repr(key(0x33)) not in rendered
    assert original.nonce_b64 not in rendered
    assert original.ciphertext_b64 not in rendered
    assert blind_index not in rendered
