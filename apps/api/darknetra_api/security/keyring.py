from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from darknetra_api.security.encryption import (
    EncryptedValue,
    SensitiveFieldConfigurationError,
    SensitiveFieldCrypto,
    decode_key_b64,
)

if TYPE_CHECKING:
    from darknetra_api.config import Settings


class SensitiveFieldKeyring:
    """Versioned runtime keyring for explicit sensitive-field maintenance.

    The object retains only decoded runtime key bytes in process memory. Its
    representation never includes key material, and no method silently rewrites
    stored envelopes.
    """

    def __init__(
        self,
        *,
        keys: Mapping[str, bytes],
        active_version: str,
        blind_index_key: bytes,
    ) -> None:
        # SensitiveFieldCrypto owns the canonical length/version validation.
        validated_boundary = SensitiveFieldCrypto(
            field_keys=keys,
            active_key_version=active_version,
            blind_index_key=blind_index_key,
        )
        self._keys = MappingProxyType({version: bytes(key) for version, key in keys.items()})
        self._active_version = validated_boundary.active_key_version
        self._blind_index_key = bytes(blind_index_key)

    def __repr__(self) -> str:
        versions = ",".join(sorted(self._keys))
        return (
            "SensitiveFieldKeyring("
            f"active_version={self._active_version!r}, key_versions={versions!r}, "
            "key_material=<redacted>)"
        )

    @property
    def active_version(self) -> str:
        return self._active_version

    @property
    def key_versions(self) -> frozenset[str]:
        return frozenset(self._keys)

    def crypto(self) -> SensitiveFieldCrypto:
        """Create an explicit crypto boundary backed by this runtime keyring."""

        return SensitiveFieldCrypto(
            field_keys=self._keys,
            active_key_version=self._active_version,
            blind_index_key=self._blind_index_key,
        )

    def reencrypt(
        self,
        value: EncryptedValue,
        *,
        purpose: str,
        resource_id: str,
    ) -> EncryptedValue:
        """Decrypt with the envelope version and encrypt with the active version."""

        boundary = self.crypto()
        plaintext = boundary.decrypt(value, purpose=purpose, resource_id=resource_id)
        try:
            return boundary.encrypt(plaintext, purpose=purpose, resource_id=resource_id)
        finally:
            # Python strings cannot be securely zeroed, but keeping scope narrow
            # prevents accidental persistence, caching or logging by this service.
            del plaintext

    @classmethod
    def from_base64_mapping(
        cls,
        *,
        keys_b64: Mapping[str, str],
        active_version: str,
        blind_index_key_b64: str,
    ) -> SensitiveFieldKeyring:
        if not keys_b64:
            raise SensitiveFieldConfigurationError(
                "at least one sensitive-field key version must be configured"
            )
        decoded: dict[str, bytes] = {}
        for version, value in keys_b64.items():
            if not isinstance(version, str) or not isinstance(value, str):
                raise SensitiveFieldConfigurationError(
                    "sensitive-field keyring must map string versions to base64 strings"
                )
            decoded[version] = decode_key_b64(
                value,
                variable=f"DARKNETRA_FIELD_KEYRING_B64_JSON[{version}]",
            )
        blind_key = decode_key_b64(
            blind_index_key_b64,
            variable="DARKNETRA_FIELD_BLIND_INDEX_KEY_B64",
        )
        return cls(
            keys=decoded,
            active_version=active_version,
            blind_index_key=blind_key,
        )

    @classmethod
    def from_json(
        cls,
        *,
        keys_json: str,
        active_version: str,
        blind_index_key_b64: str,
    ) -> SensitiveFieldKeyring:
        try:
            payload: Any = json.loads(keys_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SensitiveFieldConfigurationError(
                "DARKNETRA_FIELD_KEYRING_B64_JSON must be a JSON object"
            ) from exc
        if not isinstance(payload, dict) or not all(
            isinstance(version, str) and isinstance(value, str)
            for version, value in payload.items()
        ):
            raise SensitiveFieldConfigurationError(
                "DARKNETRA_FIELD_KEYRING_B64_JSON must map versions to base64 strings"
            )
        return cls.from_base64_mapping(
            keys_b64=payload,
            active_version=active_version,
            blind_index_key_b64=blind_index_key_b64,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> SensitiveFieldKeyring:
        if settings.field_keyring_b64_json:
            return cls.from_json(
                keys_json=settings.field_keyring_b64_json,
                active_version=settings.field_active_key_version,
                blind_index_key_b64=settings.require_field_blind_index_key_b64(),
            )
        return cls.from_base64_mapping(
            keys_b64={"v1": settings.require_field_key_v1_b64()},
            active_version=settings.field_active_key_version,
            blind_index_key_b64=settings.require_field_blind_index_key_b64(),
        )
