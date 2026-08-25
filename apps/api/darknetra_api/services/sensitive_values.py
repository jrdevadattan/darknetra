from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound, authorize_case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.encryption import EncryptedValue, SensitiveFieldCrypto
from darknetra_api.security.purposes import compose_sensitive_field_purpose
from darknetra_api.services.audit import append_audit_event


class SensitiveRevealReasonError(ValueError):
    """The justification for a full-value reveal is outside the required bounds."""


class SensitiveRevealConfigurationError(RuntimeError):
    """The owning feature did not bind its sensitive value provider and policy."""


@dataclass(frozen=True, slots=True)
class SensitiveValue:
    """One case-scoped encrypted field returned by an owning-feature provider."""

    envelope: EncryptedValue


class SensitiveValueProvider(Protocol):
    """Load one encrypted field without staging writes on the reveal session."""

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
    """Apply the owning feature's read-only resource-specific reveal policy."""

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


_SESSION_CONTEXT_KEY = "darknetra.sensitive_reveal_context"


def bind_sensitive_reveal_context(
    session: AsyncSession,
    *,
    provider: SensitiveValueProvider,
    permission_predicate: SensitiveRevealPermissionPredicate,
    crypto: SensitiveFieldCrypto,
    request_id: str,
) -> None:
    """Install one immutable owning-feature reveal binding on this request's session.

    The provider and predicate must be read-only because a successful reveal commits
    this session to make its audit event durable.
    """

    if _SESSION_CONTEXT_KEY in session.info:
        raise SensitiveRevealConfigurationError(
            "sensitive reveal dependencies are already bound to this session"
        )
    session.info[_SESSION_CONTEXT_KEY] = SensitiveRevealContext(
        provider=provider,
        permission_predicate=permission_predicate,
        crypto=crypto,
        request_id=request_id,
    )


def _get_context(session: AsyncSession) -> SensitiveRevealContext:
    context = session.info.get(_SESSION_CONTEXT_KEY)
    if not isinstance(context, SensitiveRevealContext):
        raise SensitiveRevealConfigurationError(
            "sensitive reveal dependencies must be bound by the owning feature"
        )
    return context


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise SensitiveRevealReasonError("reveal reason must be between 10 and 500 characters")
    normalized = reason.strip()
    if not 10 <= len(normalized) <= 500:
        raise SensitiveRevealReasonError("reveal reason must be between 10 and 500 characters")
    return normalized


async def _get_effective_case_roles(
    actor: User,
    case_id: UUID,
    session: AsyncSession,
) -> set[GlobalRole]:
    membership_id = await session.scalar(
        select(CaseMembership.id).where(
            CaseMembership.case_id == case_id,
            CaseMembership.user_id == actor.id,
        )
    )
    if membership_id is None:
        raise CaseNotFound("resource not found")
    membership_roles = set(
        (
            await session.scalars(
                select(CaseMembershipRole.role).where(
                    CaseMembershipRole.membership_id == membership_id
                )
            )
        ).all()
    )
    return membership_roles.intersection(set(actor.global_roles))


async def reveal_sensitive_value(
    *,
    actor: User,
    case_id: UUID,
    resource_type: str,
    resource_id: str,
    field_name: str,
    reason: str,
    session: AsyncSession,
) -> str:
    """Authorize, decrypt, durably audit, and return one explicit full-value reveal.

    Plan 03 feature adapters bind the provider, resource-specific permission
    predicate, cryptographic boundary, and request ID to the request's session.
    No plaintext is retained or copied into the audit record. A later HTTP
    endpoint is responsible for adding ``Cache-Control: no-store`` to its response.
    """

    await authorize_case(actor, case_id, Permission.CASE_READ, session)
    context = _get_context(session)
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

    effective_roles = await _get_effective_case_roles(actor, case_id, session)
    if not effective_roles or effective_roles <= {GlobalRole.VIEWER}:
        raise AuthorizationDenied("permission denied")
    if not await context.permission_predicate(
        actor=actor,
        case_id=case_id,
        resource_type=resource_type,
        resource_id=resource_id,
        field_name=field_name,
        session=session,
    ):
        raise AuthorizationDenied("permission denied")

    plaintext = context.crypto.decrypt(
        stored.envelope,
        purpose=compose_sensitive_field_purpose(resource_type, field_name),
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
