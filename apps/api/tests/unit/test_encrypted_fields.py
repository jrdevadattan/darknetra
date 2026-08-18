import base64
from dataclasses import dataclass

import pytest

from darknetra_api.security.encrypted_fields import (
    RedactionKind,
    SensitiveEnvelopeError,
    pack_envelope,
    redact_sensitive_value,
    unpack_envelope,
)
from darknetra_api.security.encryption import EncryptedValue
from pydantic import BaseModel, ConfigDict


def envelope() -> EncryptedValue:
    return EncryptedValue(
        key_version="v1",
        nonce_b64=base64.b64encode(bytes(range(12))).decode("ascii"),
        ciphertext_b64=base64.b64encode(b"ciphertext-and-tag").decode("ascii"),
    )


def test_pack_and_unpack_are_explicit_and_round_trip_without_decryption() -> None:
    value = envelope()

    packed = pack_envelope(value)

    assert packed == {
        "key_version": "v1",
        "nonce_b64": value.nonce_b64,
        "ciphertext_b64": value.ciphertext_b64,
    }
    assert unpack_envelope(packed) == value


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "required envelope fields"),
        (
            {"key_version": "v1", "nonce_b64": "not-base64", "ciphertext_b64": "YWFh"},
            "valid base64",
        ),
        (
            {
                "key_version": "v1",
                "nonce_b64": base64.b64encode(b"short").decode("ascii"),
                "ciphertext_b64": base64.b64encode(b"ciphertext-and-tag").decode("ascii"),
            },
            "12 bytes",
        ),
        (
            {
                "key_version": "v1",
                "nonce_b64": base64.b64encode(bytes(range(12))).decode("ascii"),
                "ciphertext_b64": base64.b64encode(b"tiny").decode("ascii"),
            },
            "at least 16 bytes",
        ),
    ],
)
def test_unpack_rejects_malformed_envelopes(payload: dict[str, str], message: str) -> None:
    with pytest.raises(SensitiveEnvelopeError, match=message):
        unpack_envelope(payload)


@pytest.mark.parametrize(
    "kind, value, expected",
    [
        (RedactionKind.EMAIL, "analyst@example.test", "a*****t@example.test"),
        (RedactionKind.PHONE, "+91 98765 43210", "********43210"),
        (RedactionKind.WALLET, "bc1qsyntheticwalletvalue123456", "bc1qsy…3456"),
        (RedactionKind.ONION, "syntheticexampleabcdef.onion/path", "synthe…abcdef.onion"),
        (RedactionKind.GENERAL, "authority reference", "•••••••••••••••••••"),
    ],
)
def test_redaction_is_kind_specific(kind: RedactionKind, value: str, expected: str) -> None:
    assert redact_sensitive_value(value, kind=kind) == expected


def test_empty_sensitive_value_redacts_to_empty_string() -> None:
    assert redact_sensitive_value("", kind=RedactionKind.GENERAL) == ""


@dataclass
class FakeEvidenceRow:
    id: str
    source_locator_key_version: str
    source_locator_nonce_b64: str
    source_locator_ciphertext_b64: str
    source_locator_redacted: str


class SafeEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_locator_redacted: str


def test_ordinary_pydantic_serialization_omits_envelope_internals() -> None:
    row = FakeEvidenceRow(
        id="evidence-1",
        source_locator_key_version="v1",
        source_locator_nonce_b64="nonce-secret",
        source_locator_ciphertext_b64="cipher-secret",
        source_locator_redacted="synthe…abcdef.onion",
    )

    payload = SafeEvidenceResponse.model_validate(row).model_dump()

    assert payload == {
        "id": "evidence-1",
        "source_locator_redacted": "synthe…abcdef.onion",
    }
    assert "nonce-secret" not in repr(payload)
    assert "cipher-secret" not in repr(payload)
