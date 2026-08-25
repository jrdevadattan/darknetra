from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound, authorize_case
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.encryption import EncryptedValue, SensitiveFieldCrypto
from darknetra_api.services.audit import append_audit_event


class SensitiveRevealReasonError(ValueError):
    """The justification for a full-value reveal is outside the required bounds."""


class SensitiveRevealConfigurationError(RuntimeError):
    """The owning feature did not bind its sensitive value provider and policy."""


@dataclass(frozen=True, slots=True)
class SensitiveValue:
    """An encrypted field plus the owning feature's authenticated-data purpose."""

    envelope: EncryptedValue
    purpose: str


class SensitiveValueProvider(Protocol):
    """Load one encrypted field while preserving case/resource ownership boundaries."""

    async def __call__(
        self,
        *,
        case_id: UUID,
        resource_type: str,
        resource_id: str,
        field_name: str,
        session: AsyncSession,
    ) -> SensitiveValue | None: ...


class SensitiveRevealPermissionPredicate(Protocol):
    """Apply the owning feature's resource-specific full-value reveal policy."""

    async def __call__(
        self,
        *,
        actor: User,
        case_id: UUID,
        resource_type: str,
        resource_id: str,
        field_name: str,
        session: AsyncSession,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class SensitiveRevealContext:
    """Explicit dependencies supplied by the feature that owns the encrypted field."""

    provider: SensitiveValueProvider
    permission_predicate: SensitiveRevealPermissionPredicate
    crypto: SensitiveFieldCrypto
    request_id: str


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise SensitiveRevealReasonError("reveal reason must contain 10 and 500 characters")
    normalized = reason.strip()
    if not 10 <= len(normalized) <= 500:
        raise SensitiveRevealReasonError("reveal reason must contain 10 and 500 characters")
    return normalized


def _is_viewer_only(actor: User) -> bool:
    return bool(actor.global_roles) and set(actor.global_roles) <= {GlobalRole.VIEWER}


async def reveal_sensitive_value(
    *,
    actor: User,
    case_id: UUID,
    resource_type: str,
    resource_id: str,
    field_name: str,
    reason: str,
    session: AsyncSession,
    context: SensitiveRevealContext | None = None,
) -> str:
    """Authorize, decrypt, durably audit, and return one explicit full-value reveal.

    Plan 03 feature adapters supply the provider, resource-specific permission
    predicate, cryptographic boundary, and request ID through ``context``. No
    plaintext is retained or copied into the audit record. A later HTTP endpoint
    is responsible for adding ``Cache-Control: no-store`` to its response.
    """

    await authorize_case(actor, case_id, Permission.CASE_READ, session)
    if _is_viewer_only(actor):
        raise AuthorizationDenied("permission denied")
    if context is None:
        raise SensitiveRevealConfigurationError(
            "sensitive reveal dependencies must be supplied by the owning feature"
        )
    if not await context.permission_predicate(
        actor=actor,
        case_id=case_id,
        resource_type=resource_type,
        resource_id=resource_id,
        field_name=field_name,
        session=session,
    ):
        raise AuthorizationDenied("permission denied")

    normalized_reason = _validate_reason(reason)
    stored = await context.provider(
        case_id=case_id,
        resource_type=resource_type,
        resource_id=resource_id,
        field_name=field_name,
        session=session,
    )
    if stored is None:
        raise CaseNotFound("resource not found")

    plaintext = context.crypto.decrypt(
        stored.envelope,
        purpose=stored.purpose,
        resource_id=resource_id,
    )
    append_audit_event(
        session,
        actor_user_id=actor.id,
        event_type="SENSITIVE_VALUE_REVEALED",
        resource_type=resource_type,
        resource_id=resource_id,
        case_id=case_id,
        request_id=context.request_id,
        metadata={
            "field_name": field_name,
            "reason": normalized_reason,
        },
    )
    await session.commit()
    return plaintext
