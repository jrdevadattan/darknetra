from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import CaseNotFound, authorize_case
from darknetra_api.config import get_settings
from darknetra_api.models.user import User
from darknetra_api.security.encryption import EncryptedValue, SensitiveFieldCrypto
from darknetra_api.security.keyring import SensitiveFieldKeyring
from darknetra_api.services.audit import append_audit_event


class SensitiveRevealReasonError(ValueError):
    """A full-value reveal reason is absent or outside the bounded policy."""


class SensitiveValueRegistryError(ValueError):
    """A sensitive-value resource registration is invalid or duplicated."""


class SensitiveValueResolver(Protocol):
    async def load_encrypted_value(
        self,
        *,
        session: AsyncSession,
        case_id: UUID,
        resource_id: str,
        field_name: str,
    ) -> EncryptedValue | None: ...


@dataclass(frozen=True, slots=True)
class SensitiveValueSource:
    permission: Permission
    field_purposes: Mapping[str, str]
    resolver: SensitiveValueResolver


class SensitiveValueRegistry:
    """Maps an owning resource type to its permission and explicit resolver.

    The registry contains no plaintext or key material. Plan 03 evidence models
    register their own resolver and field-purpose map rather than giving this
    generic service unrestricted reflection over ORM attributes.
    """

    def __init__(self) -> None:
        self._sources: dict[str, SensitiveValueSource] = {}

    def register(
        self,
        *,
        resource_type: str,
        permission: Permission,
        field_purposes: Mapping[str, str],
        resolver: SensitiveValueResolver,
    ) -> None:
        normalized_type = _validate_identifier(resource_type, label="resource_type")
        if normalized_type in self._sources:
            raise SensitiveValueRegistryError(
                f"sensitive-value resource type {normalized_type!r} is already registered"
            )
        if not isinstance(permission, Permission):
            raise SensitiveValueRegistryError("permission must be a Permission value")
        if not field_purposes:
            raise SensitiveValueRegistryError("at least one sensitive field purpose is required")

        validated_purposes: dict[str, str] = {}
        for field_name, purpose in field_purposes.items():
            safe_field = _validate_identifier(field_name, label="field_name")
            if not isinstance(purpose, str) or not purpose or "\x00" in purpose or ":" in purpose:
                raise SensitiveValueRegistryError(
                    "field purpose must be a non-empty string without NUL or ':'"
                )
            validated_purposes[safe_field] = purpose

        self._sources[normalized_type] = SensitiveValueSource(
            permission=permission,
            field_purposes=MappingProxyType(validated_purposes),
            resolver=resolver,
        )

    def resolve(self, resource_type: str) -> SensitiveValueSource:
        normalized_type = _validate_identifier(resource_type, label="resource_type")
        source = self._sources.get(normalized_type)
        if source is None:
            raise CaseNotFound("resource not found")
        return source


DEFAULT_SENSITIVE_VALUE_REGISTRY = SensitiveValueRegistry()


def _validate_identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 120:
        raise SensitiveValueRegistryError(f"{label} must contain 1 through 120 characters")
    if "\x00" in value or ":" in value:
        raise SensitiveValueRegistryError(f"{label} must not contain NUL or ':'")
    return value


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise SensitiveRevealReasonError("reveal reason must contain 10 through 500 characters")
    normalized = reason.strip()
    if not 10 <= len(normalized) <= 500:
        raise SensitiveRevealReasonError("reveal reason must contain 10 through 500 characters")
    return normalized


async def reveal_sensitive_value(
    *,
    actor: User,
    case_id: UUID,
    resource_type: str,
    resource_id: str,
    field_name: str,
    reason: str,
    session: AsyncSession,
    registry: SensitiveValueRegistry = DEFAULT_SENSITIVE_VALUE_REGISTRY,
    crypto: SensitiveFieldCrypto | None = None,
    request_id: str | None = None,
) -> str:
    """Authorize, decrypt and audit one explicit full-value reveal.

    The caller owns transaction commit/rollback. A later HTTP route must return
    this value with ``Cache-Control: no-store``; this service intentionally does
    not cache plaintext or expose a generic ORM decryption property.
    """

    normalized_reason = _validate_reason(reason)
    safe_resource_id = _validate_identifier(resource_id, label="resource_id")
    safe_field_name = _validate_identifier(field_name, label="field_name")
    source = registry.resolve(resource_type)

    await authorize_case(actor, case_id, source.permission, session)

    purpose = source.field_purposes.get(safe_field_name)
    if purpose is None:
        raise CaseNotFound("resource not found")
    encrypted = await source.resolver.load_encrypted_value(
        session=session,
        case_id=case_id,
        resource_id=safe_resource_id,
        field_name=safe_field_name,
    )
    if encrypted is None:
        raise CaseNotFound("resource not found")

    cryptographic_boundary = crypto or SensitiveFieldKeyring.from_settings(
        get_settings()
    ).crypto()
    plaintext = cryptographic_boundary.decrypt(
        encrypted,
        purpose=purpose,
        resource_id=safe_resource_id,
    )
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="SENSITIVE_VALUE_REVEALED",
        resource_type=resource_type,
        resource_id=safe_resource_id,
        case_id=case_id,
        request_id=request_id or str(uuid4()),
        metadata={
            "field_name": safe_field_name,
            "reason": normalized_reason,
            "key_version": encrypted.key_version,
        },
    )
    return plaintext
