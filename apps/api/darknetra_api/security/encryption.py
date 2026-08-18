from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from darknetra_api.config import Settings

_KEY_BYTES = 32
_NONCE_BYTES = 12
_MIN_GCM_PAYLOAD_BYTES = 16
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SensitiveFieldError(ValueError):
    """Base class for fail-closed sensitive-field failures."""


class SensitiveFieldConfigurationError(SensitiveFieldError):
    """Runtime key material or key selection is invalid."""


class SensitiveFieldDecryptionError(SensitiveFieldError):
    """Ciphertext could not be authenticated and decrypted."""


class UnknownKeyVersionError(SensitiveFieldDecryptionError):
    """The envelope references a key version unavailable to this process."""


@dataclass(frozen=True, repr=False)
class EncryptedValue:
    key_version: str
    nonce_b64: str
    ciphertext_b64: str

    def __repr__(self) -> str:
        return (
            "EncryptedValue("
            f"key_version={self.key_version!r}, "
            "nonce_b64='<redacted>', ciphertext_b64='<redacted>')"
        )


def decode_key_b64(value: str, *, variable: str) -> bytes:
    """Decode one required base64 key and enforce an exact 256-bit length."""

    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise SensitiveFieldConfigurationError(
            f"{variable} must contain valid base64 for exactly {_KEY_BYTES} bytes"
        ) from exc
    if len(decoded) != _KEY_BYTES:
        raise SensitiveFieldConfigurationError(
            f"{variable} must decode to exactly {_KEY_BYTES} bytes"
        )
    return decoded


def _validate_context_component(value: str, *, name: str, allow_colon: bool) -> None:
    if not isinstance(value, str) or not value:
        raise SensitiveFieldConfigurationError(f"{name} must be a non-empty string")
    if "\x00" in value or (not allow_colon and ":" in value):
        raise SensitiveFieldConfigurationError(f"{name} contains a reserved separator")


def _validate_key_version(version: str) -> None:
    if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
        raise SensitiveFieldConfigurationError("invalid sensitive-field key version")


def _decode_component(value: str, *, name: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise SensitiveFieldDecryptionError("encrypted value is invalid") from exc


class SensitiveFieldCrypto:
    """AES-256-GCM envelope encryption plus a separate HMAC blind index."""

    def __init__(
        self,
        *,
        field_keys: dict[str, bytes],
        active_key_version: str,
        blind_index_key: bytes,
    ) -> None:
        _validate_key_version(active_key_version)
        if active_key_version not in field_keys:
            raise SensitiveFieldConfigurationError(
                "active sensitive-field key version is not available"
            )
        if not field_keys:
            raise SensitiveFieldConfigurationError("at least one field key is required")
        for version, key in field_keys.items():
            _validate_key_version(version)
            if not isinstance(key, bytes) or len(key) != _KEY_BYTES:
                raise SensitiveFieldConfigurationError(
                    f"field key {version!r} must be exactly {_KEY_BYTES} bytes"
                )
        if not isinstance(blind_index_key, bytes) or len(blind_index_key) != _KEY_BYTES:
            raise SensitiveFieldConfigurationError(
                f"blind-index key must be exactly {_KEY_BYTES} bytes"
            )

        self._field_keys = dict(field_keys)
        self._active_key_version = active_key_version
        self._blind_index_key = blind_index_key

    @property
    def active_key_version(self) -> str:
        return self._active_key_version

    def _aad(self, *, purpose: str, resource_id: str, key_version: str) -> bytes:
        _validate_context_component(purpose, name="purpose", allow_colon=False)
        _validate_context_component(resource_id, name="resource_id", allow_colon=False)
        _validate_key_version(key_version)
        return f"darknetra:{purpose}:{resource_id}:{key_version}".encode()

    def encrypt(self, plaintext: str, *, purpose: str, resource_id: str) -> EncryptedValue:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be a string")
        version = self._active_key_version
        nonce = os.urandom(_NONCE_BYTES)
        aad = self._aad(purpose=purpose, resource_id=resource_id, key_version=version)
        ciphertext = AESGCM(self._field_keys[version]).encrypt(
            nonce,
            plaintext.encode(),
            aad,
        )
        return EncryptedValue(
            key_version=version,
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
        )

    def decrypt(self, value: EncryptedValue, *, purpose: str, resource_id: str) -> str:
        if not isinstance(value, EncryptedValue):
            raise SensitiveFieldDecryptionError("encrypted value is invalid")
        key = self._field_keys.get(value.key_version)
        if key is None:
            raise UnknownKeyVersionError(
                f"encrypted value references unavailable key version {value.key_version!r}"
            )
        nonce = _decode_component(value.nonce_b64, name="nonce")
        ciphertext = _decode_component(value.ciphertext_b64, name="ciphertext")
        if len(nonce) != _NONCE_BYTES or len(ciphertext) < _MIN_GCM_PAYLOAD_BYTES:
            raise SensitiveFieldDecryptionError("encrypted value is invalid")
        aad = self._aad(
            purpose=purpose,
            resource_id=resource_id,
            key_version=value.key_version,
        )
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
            return plaintext.decode()
        except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
            raise SensitiveFieldDecryptionError(
                "encrypted value could not be authenticated"
            ) from exc

    def blind_index(self, plaintext: str, *, purpose: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be a string")
        _validate_context_component(purpose, name="purpose", allow_colon=False)
        message = purpose.encode() + b"\x00" + plaintext.encode()
        return hmac.new(self._blind_index_key, message, hashlib.sha256).hexdigest()


def crypto_from_settings(settings: Settings) -> SensitiveFieldCrypto:
    """Construct the service from the complete versioned runtime keyring."""

    # Local import avoids a module cycle: the keyring reuses the primitives above.
    from darknetra_api.security.keyring import SensitiveFieldKeyring

    return SensitiveFieldKeyring.from_settings(settings).crypto()
