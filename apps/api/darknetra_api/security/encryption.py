from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from darknetra_api.config import Settings

_AES_256_KEY_BYTES = 32
_AES_GCM_NONCE_BYTES = 12
_AES_GCM_TAG_BYTES = 16


class SensitiveFieldError(RuntimeError):
    """Base error for the sensitive-field cryptographic boundary."""


class SensitiveFieldConfigurationError(SensitiveFieldError):
    """Runtime key material or key selection is invalid."""


class SensitiveFieldDecryptionError(SensitiveFieldError):
    """Ciphertext cannot be authenticated or decoded for the requested context."""


class UnknownKeyVersionError(SensitiveFieldConfigurationError):
    """An envelope refers to a key version unavailable in the runtime keyring."""


@dataclass(frozen=True, slots=True)
class EncryptedValue:
    key_version: str
    nonce_b64: str
    ciphertext_b64: str

    def __repr__(self) -> str:
        return f"EncryptedValue(key_version={self.key_version!r}, nonce=<redacted>, ciphertext=<redacted>)"


def decode_key_b64(value: str, *, variable: str) -> bytes:
    """Decode one runtime secret and require exactly 256 bits of key material."""

    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SensitiveFieldConfigurationError(f"{variable} must contain valid base64") from exc
    if len(decoded) != _AES_256_KEY_BYTES:
        raise SensitiveFieldConfigurationError(
            f"{variable} must decode to exactly {_AES_256_KEY_BYTES} bytes"
        )
    return decoded


def _validate_context_component(value: str, *, name: str, allow_colon: bool) -> None:
    if not value:
        raise ValueError(f"{name} must not be empty")
    if "\x00" in value:
        raise ValueError(f"{name} must not contain NUL characters")
    if not allow_colon and ":" in value:
        raise ValueError(f"{name} must not contain ':'")


class SensitiveFieldCrypto:
    """Explicit AES-256-GCM and keyed blind-index service.

    Plaintext is accepted and returned only at this service boundary. The class keeps
    no plaintext cache and its representation never exposes runtime key material.
    """

    def __init__(
        self,
        *,
        field_keys: Mapping[str, bytes],
        active_key_version: str,
        blind_index_key: bytes,
    ) -> None:
        _validate_context_component(active_key_version, name="active_key_version", allow_colon=False)
        validated: dict[str, bytes] = {}
        for version, key in field_keys.items():
            _validate_context_component(version, name="key version", allow_colon=False)
            if len(key) != _AES_256_KEY_BYTES:
                raise SensitiveFieldConfigurationError(
                    f"field key {version!r} must contain exactly {_AES_256_KEY_BYTES} bytes"
                )
            validated[version] = bytes(key)
        if active_key_version not in validated:
            raise UnknownKeyVersionError(
                f"active sensitive-field key version {active_key_version!r} is not configured"
            )
        if len(blind_index_key) != _AES_256_KEY_BYTES:
            raise SensitiveFieldConfigurationError(
                f"blind-index key must contain exactly {_AES_256_KEY_BYTES} bytes"
            )
        self._field_keys = validated
        self._active_key_version = active_key_version
        self._blind_index_key = bytes(blind_index_key)

    def __repr__(self) -> str:
        versions = ",".join(sorted(self._field_keys))
        return (
            "SensitiveFieldCrypto("
            f"active_key_version={self._active_key_version!r}, key_versions={versions!r}, "
            "key_material=<redacted>)"
        )

    @property
    def active_key_version(self) -> str:
        return self._active_key_version

    @property
    def key_versions(self) -> frozenset[str]:
        return frozenset(self._field_keys)

    @staticmethod
    def _aad(*, purpose: str, resource_id: str, key_version: str) -> bytes:
        _validate_context_component(purpose, name="purpose", allow_colon=False)
        _validate_context_component(resource_id, name="resource_id", allow_colon=True)
        _validate_context_component(key_version, name="key_version", allow_colon=False)
        return f"darknetra:{purpose}:{resource_id}:{key_version}".encode("utf-8")

    def encrypt(self, plaintext: str, *, purpose: str, resource_id: str) -> EncryptedValue:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be a string")
        version = self._active_key_version
        nonce = os.urandom(_AES_GCM_NONCE_BYTES)
        aad = self._aad(purpose=purpose, resource_id=resource_id, key_version=version)
        ciphertext = AESGCM(self._field_keys[version]).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            aad,
        )
        return EncryptedValue(
            key_version=version,
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
        )

    def decrypt(self, value: EncryptedValue, *, purpose: str, resource_id: str) -> str:
        key = self._field_keys.get(value.key_version)
        if key is None:
            raise UnknownKeyVersionError(
                f"sensitive-field key version {value.key_version!r} is not configured"
            )
        try:
            nonce = base64.b64decode(value.nonce_b64, validate=True)
            ciphertext = base64.b64decode(value.ciphertext_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SensitiveFieldDecryptionError("encrypted value contains invalid base64") from exc
        if len(nonce) != _AES_GCM_NONCE_BYTES or len(ciphertext) < _AES_GCM_TAG_BYTES:
            raise SensitiveFieldDecryptionError("encrypted value has invalid AES-GCM lengths")
        aad = self._aad(
            purpose=purpose,
            resource_id=resource_id,
            key_version=value.key_version,
        )
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise SensitiveFieldDecryptionError(
                "encrypted value failed authentication for the requested context"
            ) from exc

    def blind_index(self, plaintext: str, *, purpose: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be a string")
        _validate_context_component(purpose, name="purpose", allow_colon=False)
        message = purpose.encode("utf-8") + b"\x00" + plaintext.encode("utf-8")
        return hmac.new(self._blind_index_key, message, hashlib.sha256).hexdigest()


def crypto_from_settings(settings: Settings) -> SensitiveFieldCrypto:
    """Construct the service from runtime-only settings without retaining base64 strings."""

    field_key = decode_key_b64(
        settings.require_field_key_v1_b64(),
        variable="DARKNETRA_FIELD_KEY_V1_B64",
    )
    blind_key = decode_key_b64(
        settings.require_field_blind_index_key_b64(),
        variable="DARKNETRA_FIELD_BLIND_INDEX_KEY_B64",
    )
    return SensitiveFieldCrypto(
        field_keys={"v1": field_key},
        active_key_version=settings.field_active_key_version,
        blind_index_key=blind_key,
    )
