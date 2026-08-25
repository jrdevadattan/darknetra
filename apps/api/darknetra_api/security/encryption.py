import base64
import binascii
import hashlib
import hmac
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12
_KEY_VERSION_PATTERN = re.compile(r"^v[1-9][0-9]*$")


class SensitiveFieldConfigurationError(ValueError):
    """Raised when sensitive-field cryptographic configuration is invalid."""


class SensitiveFieldDecryptionError(ValueError):
    """Raised when an encrypted sensitive field cannot be authenticated."""


class UnknownKeyVersionError(SensitiveFieldDecryptionError):
    """Raised when an envelope names a key version absent from the runtime keyring."""


@dataclass(frozen=True)
class EncryptedValue:
    key_version: str
    nonce_b64: str = field(repr=False)
    ciphertext_b64: str = field(repr=False)


def decode_key_b64(value: str, *, variable: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise SensitiveFieldConfigurationError(f"{variable} must be valid base64") from exc
    if len(decoded) != KEY_BYTES:
        raise SensitiveFieldConfigurationError(f"{variable} must decode to exactly 32 bytes")
    return decoded


class SensitiveFieldCrypto:
    def __init__(
        self,
        *,
        field_keys: Mapping[str, bytes],
        active_key_version: str,
        blind_index_key: bytes,
    ) -> None:
        keys = dict(field_keys)
        if not keys:
            raise SensitiveFieldConfigurationError("at least one field key must be configured")
        for version, key in keys.items():
            if not isinstance(version, str) or not _KEY_VERSION_PATTERN.fullmatch(version):
                raise SensitiveFieldConfigurationError("invalid sensitive field key version")
            self._validate_key(key, label=f"field key {version!r}")
        self._validate_key(blind_index_key, label="blind index key")
        if active_key_version not in keys:
            raise SensitiveFieldConfigurationError("active field key version is not configured")

        self._field_keys = keys
        self._active_key_version = active_key_version
        self._blind_index_key = blind_index_key

    @property
    def active_key_version(self) -> str:
        return self._active_key_version

    @property
    def key_versions(self) -> frozenset[str]:
        return frozenset(self._field_keys)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(active_key_version={self._active_key_version!r}, "
            "field_keys=<redacted>, blind_index_key=<redacted>)"
        )

    def encrypt(self, plaintext: str, *, purpose: str, resource_id: str) -> EncryptedValue:
        key_version = self._active_key_version
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(self._field_keys[key_version]).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self._aad(purpose=purpose, resource_id=resource_id, key_version=key_version),
        )
        return EncryptedValue(
            key_version=key_version,
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
        )

    def decrypt(self, value: EncryptedValue, *, purpose: str, resource_id: str) -> str:
        try:
            key = self._field_keys[value.key_version]
        except KeyError:
            raise UnknownKeyVersionError(
                f"unknown sensitive field key version {value.key_version!r}"
            ) from None
        try:
            nonce = base64.b64decode(value.nonce_b64, validate=True)
            ciphertext = base64.b64decode(value.ciphertext_b64, validate=True)
            plaintext = AESGCM(key).decrypt(
                nonce,
                ciphertext,
                self._aad(
                    purpose=purpose,
                    resource_id=resource_id,
                    key_version=value.key_version,
                ),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, binascii.Error, TypeError, ValueError):
            raise SensitiveFieldDecryptionError("sensitive field decryption failed") from None

    def blind_index(self, plaintext: str, *, purpose: str) -> str:
        message = purpose.encode("utf-8") + b"\0" + plaintext.encode("utf-8")
        return hmac.new(self._blind_index_key, message, hashlib.sha256).hexdigest()

    @staticmethod
    def _aad(*, purpose: str, resource_id: str, key_version: str) -> bytes:
        return f"darknetra:{purpose}:{resource_id}:{key_version}".encode()

    @staticmethod
    def _validate_key(key: bytes, *, label: str) -> None:
        if not isinstance(key, bytes) or len(key) != KEY_BYTES:
            raise SensitiveFieldConfigurationError(f"{label} must be exactly 32 bytes")
