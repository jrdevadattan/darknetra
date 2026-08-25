from dataclasses import dataclass

import pytest
from darknetra_api.security.encrypted_fields import (
    EncryptedFieldValidationError,
    SensitiveFieldKind,
    pack_envelope,
    redact_for_display,
    unpack_envelope,
)
from darknetra_api.security.encryption import EncryptedValue, SensitiveFieldCrypto
from pydantic import BaseModel, ConfigDict


def key(byte: int) -> bytes:
    return bytes([byte]) * 32


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": key(0x11)},
        active_key_version="v1",
        blind_index_key=key(0x22),
    )


def test_pack_envelope_produces_explicit_persistence_columns() -> None:
    """Catches a storage mapping that drops or renames a ciphertext-envelope component."""
    envelope = EncryptedValue(
        key_version="v1",
        nonce_b64="AAECAwQFBgcICQoL",
        ciphertext_b64="AAECAwQFBgcICQoLDA0ODw==",
    )

    assert pack_envelope(envelope) == {
        "key_version": "v1",
        "nonce_b64": "AAECAwQFBgcICQoL",
        "ciphertext_b64": "AAECAwQFBgcICQoLDA0ODw==",
    }


def test_pack_envelope_rejects_malformed_envelope_values() -> None:
    """Catches callers persisting a hand-built envelope with an invalid AES-GCM nonce."""
    envelope = EncryptedValue(
        key_version="v1",
        nonce_b64="AAECAwQFBgcICQo=",
        ciphertext_b64="AAECAwQFBgcICQoLDA0ODw==",
    )

    with pytest.raises(EncryptedFieldValidationError, match="invalid encrypted field envelope"):
        pack_envelope(envelope)


def test_unpack_envelope_restores_a_valid_persisted_envelope() -> None:
    """Catches persistence reads that reconstruct the wrong envelope fields."""
    stored = {
        "key_version": "v1",
        "nonce_b64": "AAECAwQFBgcICQoL",
        "ciphertext_b64": "AAECAwQFBgcICQoLDA0ODw==",
    }

    assert unpack_envelope(stored) == EncryptedValue(**stored)


@pytest.mark.parametrize(
    "stored",
    [
        {"nonce_b64": "AAECAwQFBgcICQoL", "ciphertext_b64": "AAECAwQFBgcICQoLDA0ODw=="},
        {
            "key_version": "",
            "nonce_b64": "AAECAwQFBgcICQoL",
            "ciphertext_b64": "AAECAwQFBgcICQoLDA0ODw==",
        },
        {
            "key_version": "v1",
            "nonce_b64": "not-base64",
            "ciphertext_b64": "AAECAwQFBgcICQoLDA0ODw==",
        },
        {
            "key_version": "v1",
            "nonce_b64": "AAECAwQFBgcICQo=",
            "ciphertext_b64": "AAECAwQFBgcICQoLDA0ODw==",
        },
        {
            "key_version": "v1",
            "nonce_b64": "AAECAwQFBgcICQoL",
            "ciphertext_b64": "AAECAwQFBgcICQoL",
        },
    ],
)
def test_unpack_envelope_rejects_incomplete_or_malformed_storage(
    stored: dict[str, str],
) -> None:
    """Catches malformed persisted values reaching the decrypt-capable service boundary."""
    with pytest.raises(EncryptedFieldValidationError, match="invalid encrypted field envelope"):
        unpack_envelope(stored)


def test_unpack_envelope_never_auto_decrypts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches a persistence helper that turns ordinary reads into plaintext reveals."""
    envelope = crypto().encrypt("private@example.test", purpose="contact.email", resource_id="contact-1")

    def unexpected_decrypt(*args: object, **kwargs: object) -> str:
        raise AssertionError("ordinary envelope unpacking must not decrypt")

    monkeypatch.setattr(SensitiveFieldCrypto, "decrypt", unexpected_decrypt)

    assert unpack_envelope(pack_envelope(envelope)) == envelope


@dataclass
class PersistedContact:
    id: str
    contact_email_key_version: str
    contact_email_nonce_b64: str
    contact_email_ciphertext_b64: str
    contact_email_display: str


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_email_display: str


def test_response_schema_omits_persisted_ciphertext_internals() -> None:
    """Catches an ordinary API response schema that exposes stored envelope values."""
    stored = PersistedContact(
        id="contact-1",
        contact_email_key_version="v1",
        contact_email_nonce_b64="AAECAwQFBgcICQoL",
        contact_email_ciphertext_b64="AAECAwQFBgcICQoLDA0ODw==",
        contact_email_display="a***@example.test",
    )

    response = ContactResponse.model_validate(stored).model_dump(mode="json")

    assert response == {"id": "contact-1", "contact_email_display": "a***@example.test"}


@pytest.mark.parametrize(
    ("plaintext", "kind", "expected"),
    [
        ("alice@example.test", SensitiveFieldKind.EMAIL, "a***@example.test"),
        ("+1 (555) 123-4567", SensitiveFieldKind.PHONE, "***-***-4567"),
        ("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", SensitiveFieldKind.WALLET, "bc1qxy...x0wlh"),
        ("https://exampleonionaddress.onion/path", SensitiveFieldKind.ONION, "exampl….onion"),
        ("custody-note", SensitiveFieldKind.SECRET, "[REDACTED]"),
    ],
)
def test_redact_for_display_hides_plaintext_by_sensitive_field_kind(
    plaintext: str,
    kind: SensitiveFieldKind,
    expected: str,
) -> None:
    """Catches a display redactor that returns a full sensitive value for a supported type."""
    assert redact_for_display(plaintext, kind=kind) == expected


def test_redact_for_display_rejects_unknown_sensitive_field_kind() -> None:
    """Catches callers silently receiving an unsafe default for an unsupported field category."""
    with pytest.raises(ValueError, match="unsupported sensitive field kind"):
        redact_for_display("private@example.test", kind="passport")  # type: ignore[arg-type]
