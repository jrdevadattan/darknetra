"""Explicit persistence and display helpers for encrypted sensitive fields.

These helpers only transform an :class:`EncryptedValue` into storage values and
back. They never accept a crypto service and therefore cannot decrypt values
during ordinary ORM or response serialization. Redaction is for plaintext that
an authorized service has already obtained; callers must not retain that
plaintext after producing the display value.
"""

import base64
import binascii
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from darknetra_api.security.encryption import NONCE_BYTES, EncryptedValue

_ENVELOPE_FIELDS = ("key_version", "nonce_b64", "ciphertext_b64")
_AUTHENTICATION_TAG_BYTES = 16
_KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]{2,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9(). -]*$")
_WALLET_PATTERN = re.compile(
    r"^(?:0x[0-9a-fA-F]{40}|(?:bc|tb|bcrt)1[ac-hj-np-z02-9]{23,87}|[13][1-9A-HJ-NP-Za-km-z]{25,34})$"
)
_ONION_HOST_PATTERN = re.compile(r"^[a-z2-7]{56}\.onion$")


class EncryptedFieldValidationError(ValueError):
    """Raised when stored encrypted-field envelope data is malformed."""


class SensitiveFieldKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    WALLET = "wallet"
    ONION = "onion"
    SECRET = "secret"


def pack_envelope(value: EncryptedValue) -> dict[str, str]:
    """Return a validated envelope suitable for explicit ORM columns or JSON storage."""
    _validate_envelope(value.key_version, value.nonce_b64, value.ciphertext_b64)
    return {
        "key_version": value.key_version,
        "nonce_b64": value.nonce_b64,
        "ciphertext_b64": value.ciphertext_b64,
    }


def unpack_envelope(stored: Mapping[str, Any]) -> EncryptedValue:
    """Construct an envelope from explicit persisted values without decrypting it."""
    try:
        key_version, nonce_b64, ciphertext_b64 = (stored[field] for field in _ENVELOPE_FIELDS)
    except (KeyError, TypeError):
        raise EncryptedFieldValidationError("invalid encrypted field envelope") from None

    _validate_envelope(key_version, nonce_b64, ciphertext_b64)
    return EncryptedValue(
        key_version=key_version,
        nonce_b64=nonce_b64,
        ciphertext_b64=ciphertext_b64,
    )


def redact_for_display(plaintext: str, *, kind: SensitiveFieldKind) -> str:
    """Return a limited display value for plaintext already revealed by an authorized service."""
    if kind is SensitiveFieldKind.EMAIL:
        return _redact_email(plaintext)
    if kind is SensitiveFieldKind.PHONE:
        return _redact_phone(plaintext)
    if kind is SensitiveFieldKind.WALLET:
        return _redact_wallet(plaintext)
    if kind is SensitiveFieldKind.ONION:
        return _redact_onion(plaintext)
    if kind is SensitiveFieldKind.SECRET:
        return "[REDACTED]"
    raise ValueError("unsupported sensitive field kind")


def _validate_envelope(key_version: Any, nonce_b64: Any, ciphertext_b64: Any) -> None:
    if not isinstance(key_version, str) or not _KEY_VERSION_PATTERN.fullmatch(key_version):
        raise EncryptedFieldValidationError("invalid encrypted field envelope")
    nonce = _decode_b64(nonce_b64)
    ciphertext = _decode_b64(ciphertext_b64)
    if nonce is None or len(nonce) != NONCE_BYTES:
        raise EncryptedFieldValidationError("invalid encrypted field envelope")
    if ciphertext is None or len(ciphertext) < _AUTHENTICATION_TAG_BYTES:
        raise EncryptedFieldValidationError("invalid encrypted field envelope")


def _decode_b64(value: Any) -> bytes | None:
    if not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None


def _redact_email(plaintext: str) -> str:
    local, separator, domain = plaintext.partition("@")
    if not separator or not local or not domain or not _EMAIL_PATTERN.fullmatch(plaintext):
        return "[REDACTED]"
    return f"{local[0]}***@{domain}"


def _redact_phone(plaintext: str) -> str:
    if not _PHONE_PATTERN.fullmatch(plaintext):
        return "[REDACTED]"
    digits = "".join(character for character in plaintext if character.isdecimal())
    if not 7 <= len(digits) <= 15:
        return "[REDACTED]"
    return f"***-***-{digits[-4:]}"


def _redact_wallet(plaintext: str) -> str:
    if not _WALLET_PATTERN.fullmatch(plaintext):
        return "[REDACTED]"
    return f"{plaintext[:6]}...{plaintext[-5:]}"


def _redact_onion(plaintext: str) -> str:
    try:
        host = urlsplit(plaintext if "://" in plaintext else f"//{plaintext}").hostname
    except ValueError:
        return "[REDACTED]"
    if host is None or not _ONION_HOST_PATTERN.fullmatch(host):
        return "[REDACTED]"
    return f"{host[:6]}….onion"
