import base64

import pytest
from darknetra_api.security.encryption import (
    EncryptedValue,
    SensitiveFieldConfigurationError,
    SensitiveFieldCrypto,
    SensitiveFieldDecryptionError,
    decode_key_b64,
)
from hypothesis import given
from hypothesis import strategies as st


def key(byte: int) -> bytes:
    return bytes([byte]) * 32


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": key(0x11)},
        active_key_version="v1",
        blind_index_key=key(0x22),
    )


def test_utf8_round_trip_and_redacted_repr() -> None:
    service = crypto()
    plaintext = "ਪੰਜਾਬी source locator — 例え.onion/path"

    encrypted = service.encrypt(
        plaintext,
        purpose="evidence.source_locator",
        resource_id="evidence-001",
    )

    assert encrypted.key_version == "v1"
    assert plaintext not in repr(encrypted)
    assert service.decrypt(
        encrypted,
        purpose="evidence.source_locator",
        resource_id="evidence-001",
    ) == plaintext


def test_same_plaintext_uses_fresh_nonce_and_ciphertext() -> None:
    service = crypto()

    first = service.encrypt("same-value", purpose="contact.email", resource_id="one")
    second = service.encrypt("same-value", purpose="contact.email", resource_id="one")

    assert first.nonce_b64 != second.nonce_b64
    assert first.ciphertext_b64 != second.ciphertext_b64


def test_aad_binds_purpose_and_resource() -> None:
    service = crypto()
    encrypted = service.encrypt("secret", purpose="custody.notes", resource_id="record-a")

    with pytest.raises(SensitiveFieldDecryptionError):
        service.decrypt(encrypted, purpose="analyst.notes", resource_id="record-a")

    with pytest.raises(SensitiveFieldDecryptionError):
        service.decrypt(encrypted, purpose="custody.notes", resource_id="record-b")


def test_tampered_nonce_or_ciphertext_fails_closed() -> None:
    service = crypto()
    encrypted = service.encrypt("secret", purpose="wallet.value", resource_id="wallet-1")

    nonce = bytearray(base64.b64decode(encrypted.nonce_b64))
    nonce[0] ^= 0x01
    tampered_nonce = EncryptedValue(
        key_version=encrypted.key_version,
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
        ciphertext_b64=encrypted.ciphertext_b64,
    )
    with pytest.raises(SensitiveFieldDecryptionError):
        service.decrypt(tampered_nonce, purpose="wallet.value", resource_id="wallet-1")

    ciphertext = bytearray(base64.b64decode(encrypted.ciphertext_b64))
    ciphertext[-1] ^= 0x01
    tampered_ciphertext = EncryptedValue(
        key_version=encrypted.key_version,
        nonce_b64=encrypted.nonce_b64,
        ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
    )
    with pytest.raises(SensitiveFieldDecryptionError):
        service.decrypt(tampered_ciphertext, purpose="wallet.value", resource_id="wallet-1")


def test_blind_index_is_stable_and_purpose_scoped() -> None:
    service = crypto()

    one = service.blind_index("normalized@example.test", purpose="contact.email")
    two = service.blind_index("normalized@example.test", purpose="contact.email")
    other = service.blind_index("normalized@example.test", purpose="source.locator")

    assert one == two
    assert one != other
    assert len(one) == 64


def test_runtime_keys_must_decode_to_exactly_32_bytes() -> None:
    assert decode_key_b64(base64.b64encode(key(0x33)).decode("ascii"), variable="KEY") == key(0x33)

    with pytest.raises(SensitiveFieldConfigurationError, match="exactly 32 bytes"):
        decode_key_b64(base64.b64encode(b"short").decode("ascii"), variable="KEY")

    with pytest.raises(SensitiveFieldConfigurationError, match="valid base64"):
        decode_key_b64("not base64!", variable="KEY")


def test_constructor_rejects_non_32_byte_keys() -> None:
    with pytest.raises(SensitiveFieldConfigurationError, match="exactly 32 bytes"):
        SensitiveFieldCrypto(
            field_keys={"v1": b"short"},
            active_key_version="v1",
            blind_index_key=key(0x22),
        )

    with pytest.raises(SensitiveFieldConfigurationError, match="exactly 32 bytes"):
        SensitiveFieldCrypto(
            field_keys={"v1": key(0x11)},
            active_key_version="v1",
            blind_index_key=b"short",
        )


def test_constructor_rejects_duplicate_encryption_key_material_without_disclosure() -> None:
    reused_key = key(0x51)

    with pytest.raises(
        SensitiveFieldConfigurationError,
        match="field encryption keys must use distinct key material",
    ) as caught:
        SensitiveFieldCrypto(
            field_keys={"v1": reused_key, "v2": reused_key},
            active_key_version="v2",
            blind_index_key=key(0x52),
        )

    assert repr(reused_key) not in str(caught.value)
    assert repr(reused_key) not in repr(caught.value)


def test_constructor_rejects_blind_index_key_reuse_without_disclosure() -> None:
    reused_key = key(0x61)

    with pytest.raises(
        SensitiveFieldConfigurationError,
        match="blind index key must differ from every field encryption key",
    ) as caught:
        SensitiveFieldCrypto(
            field_keys={"v1": reused_key},
            active_key_version="v1",
            blind_index_key=reused_key,
        )

    assert repr(reused_key) not in str(caught.value)
    assert repr(reused_key) not in repr(caught.value)


def test_service_repr_errors_and_logs_do_not_expose_secrets(caplog: pytest.LogCaptureFixture) -> None:
    service = crypto()
    plaintext = "never-emit-this-plaintext"
    encrypted = service.encrypt(
        plaintext,
        purpose="custody.notes",
        resource_id="record-a",
    )

    with pytest.raises(SensitiveFieldDecryptionError) as caught:
        service.decrypt(
            encrypted,
            purpose="custody.notes",
            resource_id="wrong-record",
        )

    assert plaintext not in repr(service)
    assert repr(key(0x11)) not in repr(service)
    assert repr(key(0x22)) not in repr(service)
    assert plaintext not in str(caught.value)
    assert plaintext not in repr(caught.value)
    assert plaintext not in caplog.text


@given(plaintext=st.text(max_size=256))
def test_hypothesis_utf8_round_trip_and_envelope_byte_lengths(plaintext: str) -> None:
    service = crypto()

    encrypted = service.encrypt(
        plaintext,
        purpose="evidence.source_locator",
        resource_id="evidence-001",
    )

    assert len(base64.b64decode(encrypted.nonce_b64)) == 12
    assert len(base64.b64decode(encrypted.ciphertext_b64)) == len(plaintext.encode("utf-8")) + 16
    assert (
        service.decrypt(
            encrypted,
            purpose="evidence.source_locator",
            resource_id="evidence-001",
        )
        == plaintext
    )


@given(plaintext=st.text(max_size=128), tamper_nonce=st.booleans(), data=st.data())
def test_hypothesis_single_byte_tampering_always_fails_authentication(
    plaintext: str,
    tamper_nonce: bool,
    data: st.DataObject,
) -> None:
    service = crypto()
    encrypted = service.encrypt(
        plaintext,
        purpose="wallet.value",
        resource_id="wallet-1",
    )
    encoded = encrypted.nonce_b64 if tamper_nonce else encrypted.ciphertext_b64
    tampered = bytearray(base64.b64decode(encoded))
    offset = data.draw(st.integers(min_value=0, max_value=len(tampered) - 1))
    tampered[offset] ^= 0x01
    tampered_b64 = base64.b64encode(tampered).decode("ascii")
    value = EncryptedValue(
        key_version=encrypted.key_version,
        nonce_b64=tampered_b64 if tamper_nonce else encrypted.nonce_b64,
        ciphertext_b64=encrypted.ciphertext_b64 if tamper_nonce else tampered_b64,
    )

    with pytest.raises(SensitiveFieldDecryptionError):
        service.decrypt(value, purpose="wallet.value", resource_id="wallet-1")
