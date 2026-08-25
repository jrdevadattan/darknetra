import pytest
import sqlalchemy as sa
from darknetra_api.db.base import Base
from darknetra_api.security.encrypted_fields import (
    EncryptedFieldValidationError,
    SensitiveFieldKind,
    pack_envelope,
    redact_for_display,
    unpack_envelope,
)
from darknetra_api.security.encryption import EncryptedValue, SensitiveFieldCrypto
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Mapped, mapped_column


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


def test_unpack_envelope_rejects_noncanonical_base64_padding_bits() -> None:
    """Catches a decode-only validator accepting two spellings for the same bytes."""
    stored = {
        "key_version": "v1",
        "nonce_b64": "AAECAwQFBgcICQoL",
        "ciphertext_b64": "AAAAAAAAAAAAAAAAAAAAAB==",
    }

    with pytest.raises(EncryptedFieldValidationError, match="invalid encrypted field envelope"):
        unpack_envelope(stored)


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


class PersistedEncryptedContact(Base):
    """Focused mapped persistence record used to protect response serialization."""

    __tablename__ = "test_encrypted_contacts"

    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    contact_email_key_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    contact_email_nonce_b64: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    contact_email_ciphertext_b64: Mapped[str] = mapped_column(sa.Text, nullable=False)
    contact_email_display: Mapped[str] = mapped_column(sa.String(320), nullable=False)


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_email_display: str


def test_mapped_orm_response_omits_persisted_ciphertext_internals() -> None:
    """Catches a response schema exposing ciphertext fields from a mapped ORM record."""
    stored = PersistedEncryptedContact(
        id="contact-1",
        contact_email_key_version="v1",
        contact_email_nonce_b64="AAECAwQFBgcICQoL",
        contact_email_ciphertext_b64="AAECAwQFBgcICQoLDA0ODw==",
        contact_email_display="a***@example.test",
    )

    response = ContactResponse.model_validate(stored).model_dump(mode="json")

    assert response == {"id": "contact-1", "contact_email_display": "a***@example.test"}


def test_mapped_orm_response_never_auto_decrypts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches model validation or serialization that invokes sensitive-field decryption."""
    stored = PersistedEncryptedContact(
        id="contact-1",
        contact_email_key_version="v1",
        contact_email_nonce_b64="AAECAwQFBgcICQoL",
        contact_email_ciphertext_b64="AAECAwQFBgcICQoLDA0ODw==",
        contact_email_display="a***@example.test",
    )

    def unexpected_decrypt(*args: object, **kwargs: object) -> str:
        raise AssertionError("ordinary ORM response serialization must not decrypt")

    monkeypatch.setattr(SensitiveFieldCrypto, "decrypt", unexpected_decrypt)

    assert ContactResponse.model_validate(stored).model_dump(mode="json") == {
        "id": "contact-1",
        "contact_email_display": "a***@example.test",
    }


@pytest.mark.parametrize(
    ("plaintext", "kind", "expected"),
    [
        ("alice@example.test", SensitiveFieldKind.EMAIL, "a***@example.test"),
        ("+1 (555) 123-4567", SensitiveFieldKind.PHONE, "***-***-4567"),
        ("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", SensitiveFieldKind.WALLET, "bc1qxy...x0wlh"),
        (
            "https://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion/path",
            SensitiveFieldKind.ONION,
            "aaaaaa….onion",
        ),
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


@pytest.mark.parametrize(
    ("plaintext", "kind"),
    [
        ("a@b", SensitiveFieldKind.EMAIL),
        ("1234", SensitiveFieldKind.PHONE),
        ("12345abc", SensitiveFieldKind.PHONE),
        ("abcdefghijkl", SensitiveFieldKind.WALLET),
        ("abcdefghijklmnopqrstuvwxyz", SensitiveFieldKind.WALLET),
        ("abcdef.onion", SensitiveFieldKind.ONION),
        ("https://not-an-onion.test/path", SensitiveFieldKind.ONION),
    ],
)
def test_redact_for_display_rejects_short_or_malformed_sensitive_values(
    plaintext: str,
    kind: SensitiveFieldKind,
) -> None:
    """Catches type-specific redactors leaking full or near-full malformed plaintext."""
    assert redact_for_display(plaintext, kind=kind) == "[REDACTED]"


def test_redact_for_display_fails_closed_on_parser_invalid_onion_locator() -> None:
    """Catches malformed URL parsing escaping the redaction boundary as an exception."""
    assert redact_for_display("http://[::1", kind=SensitiveFieldKind.ONION) == "[REDACTED]"
