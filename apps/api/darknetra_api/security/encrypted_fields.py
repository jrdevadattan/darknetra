from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from darknetra_api.security.encryption import EncryptedValue

_NONCE_BYTES = 12
_MIN_CIPHERTEXT_BYTES = 16
_REQUIRED_FIELDS = frozenset({"key_version", "nonce_b64", "ciphertext_b64"})


class SensitiveEnvelopeError(ValueError):
    """An encrypted persistence envelope is malformed or incomplete."""


class RedactionKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    WALLET = "wallet"
    ONION = "onion"
    GENERAL = "general"


def pack_envelope(value: EncryptedValue) -> dict[str, str]:
    """Convert a typed envelope into explicit persistence fields.

    This helper intentionally performs no decryption and returns no plaintext-derived
    values. Owning services decide whether to store these fields as columns or JSON.
    """

    return {
        "key_version": value.key_version,
        "nonce_b64": value.nonce_b64,
        "ciphertext_b64": value.ciphertext_b64,
    }


def _decode_b64(value: str, *, field: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SensitiveEnvelopeError(f"{field} must contain valid base64") from exc


def unpack_envelope(payload: Mapping[str, Any]) -> EncryptedValue:
    """Validate persisted envelope fields without decrypting them."""

    missing = _REQUIRED_FIELDS.difference(payload)
    if missing:
        raise SensitiveEnvelopeError(
            "required envelope fields are missing: " + ", ".join(sorted(missing))
        )

    key_version = payload["key_version"]
    nonce_b64 = payload["nonce_b64"]
    ciphertext_b64 = payload["ciphertext_b64"]
    if not isinstance(key_version, str) or not key_version or ":" in key_version:
        raise SensitiveEnvelopeError("key_version must be a non-empty version identifier")
    if not isinstance(nonce_b64, str) or not isinstance(ciphertext_b64, str):
        raise SensitiveEnvelopeError("envelope base64 fields must be strings")

    nonce = _decode_b64(nonce_b64, field="nonce_b64")
    ciphertext = _decode_b64(ciphertext_b64, field="ciphertext_b64")
    if len(nonce) != _NONCE_BYTES:
        raise SensitiveEnvelopeError(f"nonce_b64 must decode to {_NONCE_BYTES} bytes")
    if len(ciphertext) < _MIN_CIPHERTEXT_BYTES:
        raise SensitiveEnvelopeError(
            f"ciphertext_b64 must decode to at least {_MIN_CIPHERTEXT_BYTES} bytes"
        )

    return EncryptedValue(
        key_version=key_version,
        nonce_b64=nonce_b64,
        ciphertext_b64=ciphertext_b64,
    )


def _redact_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator or not local or not domain:
        return "•" * len(value)
    if len(local) == 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * (len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"


def _redact_phone(value: str) -> str:
    compact = "".join(character for character in value if not character.isspace())
    if len(compact) <= 5:
        return "*" * len(compact)
    return ("*" * (len(compact) - 5)) + compact[-5:]


def _redact_wallet(value: str) -> str:
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:6]}…{value[-4:]}"


def _redact_onion(value: str) -> str:
    host = value.split("/", maxsplit=1)[0]
    lowered = host.casefold()
    if not lowered.endswith(".onion"):
        return "•" * len(value)
    label = host[: -len(".onion")]
    if len(label) <= 12:
        masked = "•" * len(label)
    else:
        masked = f"{label[:6]}…{label[-6:]}"
    return f"{masked}.onion"


def redact_sensitive_value(value: str, *, kind: RedactionKind) -> str:
    """Create a display-only redaction while plaintext is in authorized local scope."""

    if not isinstance(value, str):
        raise TypeError("sensitive value must be a string")
    if not value:
        return ""
    if kind is RedactionKind.EMAIL:
        return _redact_email(value)
    if kind is RedactionKind.PHONE:
        return _redact_phone(value)
    if kind is RedactionKind.WALLET:
        return _redact_wallet(value)
    if kind is RedactionKind.ONION:
        return _redact_onion(value)
    return "•" * len(value)
