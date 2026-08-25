from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from darknetra_api.security.encryption import (
    EncryptedValue,
    SensitiveFieldConfigurationError,
    SensitiveFieldCrypto,
    UnknownKeyVersionError,
    decode_key_b64,
)

if TYPE_CHECKING:
    from darknetra_api.config import Settings

_KEYRING_VARIABLE = "DARKNETRA_FIELD_KEYRING_B64_JSON"
_LEGACY_V1_VARIABLE = "DARKNETRA_FIELD_KEY_V1_B64"
_BLIND_INDEX_VARIABLE = "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64"


@dataclass(frozen=True)
class SensitiveFieldRotationResult:
    """Explicit replacement values produced by one maintenance rotation."""

    value: EncryptedValue
    blind_index: str = field(repr=False)


class SensitiveFieldKeyring:
    """Immutable runtime key versions used by explicit maintenance operations."""

    def __init__(
        self,
        *,
        keys: Mapping[str, bytes],
        active_version: str,
        blind_index_key: bytes,
    ) -> None:
        validated = SensitiveFieldCrypto(
            field_keys=keys,
            active_key_version=active_version,
            blind_index_key=blind_index_key,
        )
        self._keys = MappingProxyType(
            {version: bytes(key) for version, key in keys.items()}
        )
        self._active_version = validated.active_key_version
        self._blind_index_key = bytes(blind_index_key)

    def __repr__(self) -> str:
        versions = ",".join(sorted(self._keys))
        return (
            f"{type(self).__name__}(active_version={self._active_version!r}, "
            f"key_versions={versions!r}, key_material=<redacted>)"
        )

    @property
    def active_version(self) -> str:
        return self._active_version

    @property
    def key_versions(self) -> frozenset[str]:
        return frozenset(self._keys)

    def crypto(self) -> SensitiveFieldCrypto:
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
        """Decrypt by envelope version and encrypt a fresh active-version envelope."""

        boundary = self.crypto()
        plaintext = boundary.decrypt(value, purpose=purpose, resource_id=resource_id)
        try:
            return boundary.encrypt(plaintext, purpose=purpose, resource_id=resource_id)
        finally:
            del plaintext

    @classmethod
    def from_base64_mapping(
        cls,
        *,
        keys_b64: Mapping[str, str],
        active_version: str,
        blind_index_key_b64: str,
    ) -> SensitiveFieldKeyring:
        decoded = _decode_base64_mapping(keys_b64)
        return cls(
            keys=decoded,
            active_version=active_version,
            blind_index_key=decode_key_b64(
                blind_index_key_b64,
                variable=_BLIND_INDEX_VARIABLE,
            ),
        )

    @classmethod
    def from_json(
        cls,
        *,
        keys_json: str,
        active_version: str,
        blind_index_key_b64: str,
    ) -> SensitiveFieldKeyring:
        return cls.from_base64_mapping(
            keys_b64=_parse_json_mapping(keys_json),
            active_version=active_version,
            blind_index_key_b64=blind_index_key_b64,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> SensitiveFieldKeyring:
        if not settings.field_blind_index_key_b64:
            raise SensitiveFieldConfigurationError(
                f"{_BLIND_INDEX_VARIABLE} must be configured"
            )

        keys_b64: dict[str, str]
        if settings.field_keyring_b64_json:
            keys_b64 = _parse_json_mapping(settings.field_keyring_b64_json)
            if settings.field_key_v1_b64:
                configured_v1 = keys_b64.get("v1")
                if configured_v1 is not None and configured_v1 != settings.field_key_v1_b64:
                    raise SensitiveFieldConfigurationError(
                        "conflicting v1 sensitive field keys are configured"
                    )
                keys_b64.setdefault("v1", settings.field_key_v1_b64)
        elif settings.field_key_v1_b64:
            keys_b64 = {"v1": settings.field_key_v1_b64}
        else:
            raise SensitiveFieldConfigurationError(
                f"{_LEGACY_V1_VARIABLE} must be configured"
            )

        return cls.from_base64_mapping(
            keys_b64=keys_b64,
            active_version=settings.field_active_key_version,
            blind_index_key_b64=settings.field_blind_index_key_b64,
        )


def rotate_sensitive_field(
    *,
    value: EncryptedValue,
    blind_index: str,
    purpose: str,
    resource_id: str,
    keyring: SensitiveFieldKeyring,
    rotate_blind_index: bool = False,
) -> SensitiveFieldRotationResult:
    """Return explicit replacement values for authorized offline/admin maintenance.

    This primitive has no persistence side effect. The maintenance caller must
    authorize the operation, write the returned values transactionally, and
    preserve immutable audit/history rows.
    """

    boundary = keyring.crypto()
    plaintext = boundary.decrypt(value, purpose=purpose, resource_id=resource_id)
    try:
        rotated_index = (
            boundary.blind_index(plaintext, purpose=purpose)
            if rotate_blind_index
            else blind_index
        )
        return SensitiveFieldRotationResult(
            value=boundary.encrypt(plaintext, purpose=purpose, resource_id=resource_id),
            blind_index=rotated_index,
        )
    finally:
        del plaintext


def validate_keyring_b64_json(value: str) -> None:
    """Validate the serialized runtime mapping without retaining decoded keys."""

    _decode_base64_mapping(_parse_json_mapping(value))


def _parse_json_mapping(value: str) -> dict[str, str]:
    try:
        payload: Any = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SensitiveFieldConfigurationError(
            f"{_KEYRING_VARIABLE} must be a JSON object"
        ) from exc
    if not isinstance(payload, dict) or not payload or not all(
        isinstance(version, str) and isinstance(encoded, str)
        for version, encoded in payload.items()
    ):
        raise SensitiveFieldConfigurationError(
            f"{_KEYRING_VARIABLE} must map key versions to base64 strings"
        )
    return payload


def _decode_base64_mapping(keys_b64: Mapping[str, str]) -> dict[str, bytes]:
    if not keys_b64:
        raise SensitiveFieldConfigurationError(
            "at least one sensitive field key version must be configured"
        )
    return {
        version: decode_key_b64(
            encoded,
            variable=f"{_KEYRING_VARIABLE}[{version}]",
        )
        for version, encoded in keys_b64.items()
    }


__all__ = [
    "SensitiveFieldKeyring",
    "SensitiveFieldRotationResult",
    "UnknownKeyVersionError",
    "rotate_sensitive_field",
]
