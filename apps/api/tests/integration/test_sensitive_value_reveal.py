from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseSensitivity, GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.encryption import EncryptedValue, SensitiveFieldCrypto
from darknetra_api.services.sensitive_values import (
    SensitiveRevealReasonError,
    SensitiveValueRegistry,
    reveal_sensitive_value,
)

PLAINTEXT = "synthetic-source-identifier.onion/path"


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": bytes([0x31]) * 32},
        active_key_version="v1",
        blind_index_key=bytes([0x32]) * 32,
    )


@dataclass
class StaticResolver:
    envelope: EncryptedValue
    case_id: UUID
    resource_id: str = "evidence-001"
    field_name: str = "source_locator"

    async def load_encrypted_value(
        self,
        *,
        session: object,
        case_id: UUID,
        resource_id: str,
        field_name: str,
    ) -> EncryptedValue | None:
        del session
        if (
            case_id == self.case_id
            and resource_id == self.resource_id
            and field_name == self.field_name
        ):
            return self.envelope
        return None


@pytest.fixture(autouse=True)
async def clean_sensitive_reveal_state() -> None:
    async with async_session_factory() as session:
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(CaseMembershipRole))
        await session.execute(sa.delete(CaseMembership))
        await session.execute(sa.delete(Case))
        await session.execute(sa.delete(AuthSession))
        await session.execute(sa.delete(User))
        await session.commit()
    yield
    async with async_session_factory() as session:
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(CaseMembershipRole))
        await session.execute(sa.delete(CaseMembership))
        await session.execute(sa.delete(Case))
        await session.execute(sa.delete(AuthSession))
        await session.execute(sa.delete(User))
        await session.commit()


async def seed_actor_with_case(*, role: GlobalRole, case_code: str) -> tuple[User, Case]:
    async with async_session_factory() as session:
        actor = User(
            username=f"{role.value.lower()}-{case_code.lower()}",
            username_normalized=f"{role.value.lower()}-{case_code.lower()}",
            display_name=f"Synthetic {role.value}",
            password_hash="not-used-in-this-test",
            global_roles=[role],
            is_active=True,
            must_change_password=False,
        )
        session.add(actor)
        await session.flush()
        case = Case(
            case_code=case_code,
            title=f"Synthetic case {case_code}",
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=actor.id,
            source_authority_summary="Authorized synthetic integration test",
        )
        session.add(case)
        await session.flush()
        membership = CaseMembership(case_id=case.id, user_id=actor.id)
        session.add(membership)
        await session.flush()
        session.add(CaseMembershipRole(membership_id=membership.id, role=role))
        await session.commit()
        await session.refresh(actor)
        await session.refresh(case)
        return actor, case


def registry_for(case_id: UUID, service: SensitiveFieldCrypto) -> SensitiveValueRegistry:
    envelope = service.encrypt(
        PLAINTEXT,
        purpose="evidence.source_locator",
        resource_id="evidence-001",
    )
    registry = SensitiveValueRegistry()
    registry.register(
        resource_type="evidence",
        permission=Permission.SENSITIVE_VALUE_REVEAL,
        field_purposes={"source_locator": "evidence.source_locator"},
        resolver=StaticResolver(envelope=envelope, case_id=case_id),
    )
    return registry


@pytest.mark.integration
@pytest.mark.asyncio
async def test_viewer_is_denied_sensitive_reveal_without_audit() -> None:
    viewer, case = await seed_actor_with_case(role=GlobalRole.VIEWER, case_code="SVR-VIEW")
    service = crypto()

    async with async_session_factory() as session:
        with pytest.raises(AuthorizationDenied):
            await reveal_sensitive_value(
                actor=viewer,
                case_id=case.id,
                resource_type="evidence",
                resource_id="evidence-001",
                field_name="source_locator",
                reason="Investigative review of a protected source locator",
                session=session,
                registry=registry_for(case.id, service),
                crypto=service,
                request_id="request-viewer-denied",
            )
        assert await session.scalar(sa.select(sa.func.count(AuditEvent.id))) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_case_reveal_matches_repository_not_found_policy() -> None:
    analyst, visible_case = await seed_actor_with_case(role=GlobalRole.ANALYST, case_code="SVR-A")
    _, other_case = await seed_actor_with_case(role=GlobalRole.REVIEWER, case_code="SVR-B")
    service = crypto()

    async with async_session_factory() as session:
        with pytest.raises(CaseNotFound, match="resource not found"):
            await reveal_sensitive_value(
                actor=analyst,
                case_id=other_case.id,
                resource_type="evidence",
                resource_id="evidence-001",
                field_name="source_locator",
                reason="Investigative review of a protected source locator",
                session=session,
                registry=registry_for(other_case.id, service),
                crypto=service,
                request_id="request-cross-case",
            )
        assert visible_case.id != other_case.id


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "short", "x" * 501])
async def test_reveal_reason_must_be_bounded(reason: str) -> None:
    analyst, case = await seed_actor_with_case(role=GlobalRole.ANALYST, case_code="SVR-REASON")
    service = crypto()

    async with async_session_factory() as session:
        with pytest.raises(SensitiveRevealReasonError, match="10 through 500"):
            await reveal_sensitive_value(
                actor=analyst,
                case_id=case.id,
                resource_type="evidence",
                resource_id="evidence-001",
                field_name="source_locator",
                reason=reason,
                session=session,
                registry=registry_for(case.id, service),
                crypto=service,
                request_id="request-bad-reason",
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authorized_reveal_returns_plaintext_and_audits_only_context() -> None:
    analyst, case = await seed_actor_with_case(role=GlobalRole.ANALYST, case_code="SVR-OK")
    service = crypto()
    reason = "Correlate the protected source locator with authorized case material"

    async with async_session_factory() as session:
        value = await reveal_sensitive_value(
            actor=analyst,
            case_id=case.id,
            resource_type="evidence",
            resource_id="evidence-001",
            field_name="source_locator",
            reason=reason,
            session=session,
            registry=registry_for(case.id, service),
            crypto=service,
            request_id="request-success",
        )
        assert value == PLAINTEXT
        await session.commit()

    async with async_session_factory() as session:
        event = await session.scalar(
            sa.select(AuditEvent).where(AuditEvent.event_type == "SENSITIVE_VALUE_REVEALED")
        )
        assert event is not None
        assert event.actor_user_id == analyst.id
        assert event.case_id == case.id
        assert event.resource_type == "evidence"
        assert event.resource_id == "evidence-001"
        assert event.request_id == "request-success"
        assert event.metadata_json == {
            "field_name": "source_locator",
            "reason": reason,
            "key_version": "v1",
        }
        assert PLAINTEXT not in repr(event.metadata_json)
