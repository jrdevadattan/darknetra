import importlib
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseSensitivity, CaseStatus, GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.encryption import SensitiveFieldCrypto
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def reveal_module() -> Any:
    return importlib.import_module("darknetra_api.services.sensitive_values")


def make_user(username: str, *roles: GlobalRole) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=username,
        password_hash="not-used",
        global_roles=list(roles),
        is_active=True,
        must_change_password=False,
    )


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": bytes([0x33]) * 32},
        active_key_version="v1",
        blind_index_key=bytes([0x44]) * 32,
    )


class FixtureProvider:
    def __init__(self, records: dict[tuple[UUID, str, str, str], object]) -> None:
        self.records = records
        self.calls: list[tuple[UUID, str, str, str]] = []

    async def __call__(
        self,
        *,
        case_id: UUID,
        resource_type: str,
        resource_id: str,
        field_name: str,
        session: object,
    ) -> object | None:
        del session
        key = (case_id, resource_type, resource_id, field_name)
        self.calls.append(key)
        return self.records.get(key)


class OwningFeaturePolicy:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, **kwargs: object) -> bool:
        del kwargs
        self.calls += 1
        return True


async def clear_state() -> None:
    async with async_session_factory() as session:
        for model in (
            AuditEvent,
            CaseMembershipRole,
            CaseMembership,
            Case,
            AuthSession,
            User,
        ):
            await session.execute(sa.delete(model))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    await clear_state()
    yield
    await clear_state()


async def add_membership(
    session: AsyncSession,
    case: Case,
    user: User,
    role: GlobalRole,
) -> None:
    membership = CaseMembership(case_id=case.id, user_id=user.id)
    session.add(membership)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=membership.id, role=role))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_effective_roles_scoped_not_found_and_audit_transaction() -> None:
    """Exercises persisted effective roles, scoped 404 equivalence, and audited reveal."""
    module = reveal_module()
    crypto_service = crypto()
    visible_resource_id = "evidence-integration-reveal"
    cross_case_resource_id = "evidence-other-case"
    plaintext = "https://integration-private.example/source"

    async with async_session_factory() as session:
        owner = make_user("sensitive-owner", GlobalRole.CASE_OWNER)
        mixed_viewer = make_user(
            "sensitive-mixed-viewer",
            GlobalRole.VIEWER,
            GlobalRole.ANALYST,
        )
        outsider = make_user("sensitive-outsider", GlobalRole.ANALYST)
        session.add_all([owner, mixed_viewer, outsider])
        await session.flush()
        visible_case = Case(
            case_code="SENSITIVE-VISIBLE",
            title="Visible sensitive case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic integration fixture",
        )
        hidden_case = Case(
            case_code="SENSITIVE-HIDDEN",
            title="Hidden sensitive case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=outsider.id,
            source_authority_summary="Synthetic integration fixture",
        )
        session.add_all([visible_case, hidden_case])
        await session.flush()
        await add_membership(session, visible_case, owner, GlobalRole.CASE_OWNER)
        await add_membership(session, visible_case, mixed_viewer, GlobalRole.VIEWER)
        await add_membership(session, hidden_case, outsider, GlobalRole.ANALYST)
        await session.commit()

        visible_stored = module.SensitiveValue(
            envelope=crypto_service.encrypt(
                plaintext,
                purpose='darknetra-sensitive-reveal:v1:["evidence","source_locator"]',
                resource_id=visible_resource_id,
            )
        )
        cross_case_stored = module.SensitiveValue(
            envelope=crypto_service.encrypt(
                "other-case-secret",
                purpose='darknetra-sensitive-reveal:v1:["evidence","source_locator"]',
                resource_id=cross_case_resource_id,
            )
        )
        provider = FixtureProvider(
            {
                (
                    visible_case.id,
                    "evidence",
                    visible_resource_id,
                    "source_locator",
                ): visible_stored,
                (
                    hidden_case.id,
                    "evidence",
                    cross_case_resource_id,
                    "source_locator",
                ): cross_case_stored,
            }
        )
        policy = OwningFeaturePolicy()
        module.bind_sensitive_reveal_context(
            session,
            provider=provider,
            permission_predicate=policy,
            crypto=crypto_service,
            request_id="request-integration-reveal",
        )

        with pytest.raises(AuthorizationDenied, match="permission denied"):
            await module.reveal_sensitive_value(
                actor=mixed_viewer,
                case_id=visible_case.id,
                resource_type="evidence",
                resource_id=visible_resource_id,
                field_name="source_locator",
                reason="Mixed global roles must use effective case membership",
                session=session,
            )

        resource_outcomes: list[tuple[type[BaseException], tuple[object, ...]]] = []
        for resource_id in (cross_case_resource_id, "evidence-unknown"):
            with pytest.raises(CaseNotFound) as caught:
                await module.reveal_sensitive_value(
                    actor=owner,
                    case_id=visible_case.id,
                    resource_type="evidence",
                    resource_id=resource_id,
                    field_name="source_locator",
                    reason="Cross-case and unknown resources must share one outcome",
                    session=session,
                )
            resource_outcomes.append((type(caught.value), caught.value.args))

        assert resource_outcomes == [
            (CaseNotFound, ("resource not found",)),
            (CaseNotFound, ("resource not found",)),
        ]
        assert policy.calls == 0

        revealed = await module.reveal_sensitive_value(
            actor=owner,
            case_id=visible_case.id,
            resource_type="evidence",
            resource_id=visible_resource_id,
            field_name="source_locator",
            reason="Validate original source provenance",
            session=session,
        )

        assert revealed == plaintext
        assert policy.calls == 1
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "SENSITIVE_VALUE_REVEALED")
        )
        assert event is not None
        assert event.actor_user_id == owner.id
        assert event.case_id == visible_case.id
        assert event.resource_type == "evidence"
        assert event.resource_id == visible_resource_id
        assert event.metadata_json == {
            "field_name": "source_locator",
            "reason": "Validate original source provenance",
        }
        assert plaintext not in repr(event.__dict__)
