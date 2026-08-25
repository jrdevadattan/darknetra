import importlib
from collections.abc import Awaitable, Callable
from typing import Any

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


def reveal_module() -> Any:
    return importlib.import_module("darknetra_api.services.sensitive_values")


def make_user(username: str, role: GlobalRole) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=username,
        password_hash="not-used",
        global_roles=[role],
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
    def __init__(self, records: dict[tuple[object, str, str, str], object]) -> None:
        self.records = records
        self.calls = 0

    async def __call__(
        self,
        *,
        case_id: object,
        resource_type: str,
        resource_id: str,
        field_name: str,
        session: object,
    ) -> object | None:
        del session
        self.calls += 1
        return self.records.get((case_id, resource_type, resource_id, field_name))


PermissionPredicate = Callable[..., Awaitable[bool]]


async def owning_feature_policy(*, actor: User, **kwargs: object) -> bool:
    del kwargs
    return GlobalRole.VIEWER not in actor.global_roles


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


async def add_membership(session: object, case: Case, user: User, role: GlobalRole) -> None:
    session.add(CaseMembership(case_id=case.id, user_id=user.id))  # type: ignore[attr-defined]
    await session.flush()  # type: ignore[attr-defined]
    membership = await session.scalar(  # type: ignore[attr-defined]
        select(CaseMembership).where(
            CaseMembership.case_id == case.id,
            CaseMembership.user_id == user.id,
        )
    )
    session.add(CaseMembershipRole(membership_id=membership.id, role=role))  # type: ignore[attr-defined]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_case_authorization_policy_and_audit_transaction() -> None:
    """Catches reveal authorization drifting from persisted case membership and audit behavior."""
    module = reveal_module()
    crypto_service = crypto()
    resource_id = "evidence-integration-reveal"
    plaintext = "https://integration-private.example/source"

    async with async_session_factory() as session:
        owner = make_user("sensitive-owner", GlobalRole.CASE_OWNER)
        viewer = make_user("sensitive-viewer", GlobalRole.VIEWER)
        outsider = make_user("sensitive-outsider", GlobalRole.ANALYST)
        session.add_all([owner, viewer, outsider])
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
        await add_membership(session, visible_case, viewer, GlobalRole.VIEWER)
        await add_membership(session, hidden_case, outsider, GlobalRole.ANALYST)
        await session.commit()

        stored = module.SensitiveValue(
            envelope=crypto_service.encrypt(
                plaintext,
                purpose="evidence.source_locator",
                resource_id=resource_id,
            ),
            purpose="evidence.source_locator",
        )
        provider = FixtureProvider(
            {
                (
                    visible_case.id,
                    "evidence",
                    resource_id,
                    "source_locator",
                ): stored
            }
        )
        context = module.SensitiveRevealContext(
            provider=provider,
            permission_predicate=owning_feature_policy,
            crypto=crypto_service,
            request_id="request-integration-reveal",
        )

        with pytest.raises(AuthorizationDenied, match="permission denied"):
            await module.reveal_sensitive_value(
                actor=viewer,
                case_id=visible_case.id,
                resource_type="evidence",
                resource_id=resource_id,
                field_name="source_locator",
                reason="Viewer must not reveal this value",
                session=session,
                context=context,
            )

        with pytest.raises(CaseNotFound, match="resource not found"):
            await module.reveal_sensitive_value(
                actor=owner,
                case_id=hidden_case.id,
                resource_type="evidence",
                resource_id=resource_id,
                field_name="source_locator",
                reason="Cross-case access must remain hidden",
                session=session,
                context=context,
            )

        revealed = await module.reveal_sensitive_value(
            actor=owner,
            case_id=visible_case.id,
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Validate original source provenance",
            session=session,
            context=context,
        )

        assert revealed == plaintext
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "SENSITIVE_VALUE_REVEALED")
        )
        assert event is not None
        assert event.actor_user_id == owner.id
        assert event.case_id == visible_case.id
        assert event.resource_type == "evidence"
        assert event.resource_id == resource_id
        assert event.metadata_json == {
            "field_name": "source_locator",
            "reason": "Validate original source provenance",
        }
        assert plaintext not in repr(event.__dict__)
