import importlib
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import pytest
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.encryption import SensitiveFieldCrypto


def reveal_module() -> Any:
    return importlib.import_module("darknetra_api.services.sensitive_values")


def make_user(role: GlobalRole) -> User:
    return User(
        username=f"{role.value.casefold()}-user",
        username_normalized=f"{role.value.casefold()}-user",
        display_name=f"{role.value} User",
        password_hash="not-used",
        global_roles=[role],
        is_active=True,
        must_change_password=False,
    )


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": bytes([0x11]) * 32},
        active_key_version="v1",
        blind_index_key=bytes([0x22]) * 32,
    )


class FakeSession:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.added: list[object] = []
        self.committed = False
        self.commit_error = commit_error

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True


class TrackingProvider:
    def __init__(self, value: object | None) -> None:
        self.value = value
        self.calls = 0

    async def __call__(self, **kwargs: object) -> object | None:
        del kwargs
        self.calls += 1
        return self.value


class TrackingCrypto:
    def __init__(self, delegate: SensitiveFieldCrypto) -> None:
        self.delegate = delegate
        self.decrypt_calls = 0

    def decrypt(self, *args: object, **kwargs: object) -> str:
        self.decrypt_calls += 1
        return self.delegate.decrypt(*args, **kwargs)  # type: ignore[arg-type]


PermissionPredicate = Callable[..., Awaitable[bool]]


async def allow_reveal(**kwargs: object) -> bool:
    del kwargs
    return True


async def deny_reveal(**kwargs: object) -> bool:
    del kwargs
    return False


def make_context(
    *,
    provider: TrackingProvider,
    permission: PermissionPredicate = allow_reveal,
    crypto_service: object | None = None,
    request_id: str = "request-sensitive-reveal",
) -> object:
    module = reveal_module()
    return module.SensitiveRevealContext(
        provider=provider,
        permission_predicate=permission,
        crypto=crypto_service or crypto(),
        request_id=request_id,
    )


def encrypted_value(*, plaintext: str, resource_id: str) -> tuple[object, SensitiveFieldCrypto]:
    module = reveal_module()
    crypto_service = crypto()
    envelope = crypto_service.encrypt(
        plaintext,
        purpose="evidence.source_locator",
        resource_id=resource_id,
    )
    return (
        module.SensitiveValue(
            envelope=envelope,
            purpose="evidence.source_locator",
        ),
        crypto_service,
    )


@pytest.mark.asyncio
async def test_viewer_is_denied_before_provider_lookup_or_decryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a permissive owning-feature predicate granting a VIEWER full-value access."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)
    resource_id = "evidence-viewer-denied"
    stored, crypto_service = encrypted_value(plaintext="viewer-secret", resource_id=resource_id)
    provider = TrackingProvider(stored)
    tracking_crypto = TrackingCrypto(crypto_service)

    with pytest.raises(AuthorizationDenied, match="permission denied"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.VIEWER),
            case_id=uuid4(),
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Investigating source provenance",
            session=FakeSession(),
            context=make_context(
                provider=provider,
                permission=allow_reveal,
                crypto_service=tracking_crypto,
            ),
        )

    assert provider.calls == 0
    assert tracking_crypto.decrypt_calls == 0


@pytest.mark.asyncio
async def test_owning_feature_permission_predicate_can_deny_non_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches the service bypassing the owning feature's resource-specific reveal policy."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)
    provider = TrackingProvider(None)

    with pytest.raises(AuthorizationDenied, match="permission denied"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=uuid4(),
            resource_type="evidence",
            resource_id="evidence-policy-denied",
            field_name="source_locator",
            reason="Investigating source provenance",
            session=FakeSession(),
            context=make_context(provider=provider, permission=deny_reveal),
        )

    assert provider.calls == 0


@pytest.mark.asyncio
async def test_inaccessible_and_unknown_cases_share_not_found_outcome_before_reason_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches validation or lookup leaking whether an inaccessible case exists."""
    module = reveal_module()
    provider = TrackingProvider(None)

    async def not_found(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise CaseNotFound("resource not found")

    monkeypatch.setattr(module, "authorize_case", not_found)
    outcomes: list[tuple[type[BaseException], tuple[object, ...]]] = []
    for case_id in (uuid4(), uuid4()):
        with pytest.raises(CaseNotFound) as caught:
            await module.reveal_sensitive_value(
                actor=make_user(GlobalRole.ANALYST),
                case_id=case_id,
                resource_type="evidence",
                resource_id="evidence-hidden",
                field_name="source_locator",
                reason="short",
                session=FakeSession(),
                context=make_context(provider=provider),
            )
        outcomes.append((type(caught.value), caught.value.args))

    assert outcomes == [
        (CaseNotFound, ("resource not found",)),
        (CaseNotFound, ("resource not found",)),
    ]
    assert provider.calls == 0


@pytest.mark.parametrize("reason", ["", " " * 20, "123456789", "x" * 501])
@pytest.mark.asyncio
async def test_reason_must_be_between_10_and_500_trimmed_characters(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Catches blank, too-short, or overlong justifications reaching the decrypt boundary."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)
    provider = TrackingProvider(None)

    with pytest.raises(module.SensitiveRevealReasonError, match="10 and 500"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=uuid4(),
            resource_type="evidence",
            resource_id="evidence-invalid-reason",
            field_name="source_locator",
            reason=reason,
            session=FakeSession(),
            context=make_context(provider=provider),
        )

    assert provider.calls == 0


@pytest.mark.asyncio
async def test_provider_miss_uses_repository_standard_not_found_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a case-scoped resource miss exposing a provider-specific result or error."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)

    with pytest.raises(CaseNotFound, match="resource not found"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=uuid4(),
            resource_type="evidence",
            resource_id="evidence-missing",
            field_name="source_locator",
            reason="Investigating source provenance",
            session=FakeSession(),
            context=make_context(provider=TrackingProvider(None)),
        )


@pytest.mark.parametrize("reason", ["x" * 10, "x" * 500])
@pytest.mark.asyncio
async def test_reason_accepts_inclusive_policy_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Catches exclusive-bound validation rejecting a policy-valid reveal reason."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)
    resource_id = "evidence-reason-boundary"
    stored, crypto_service = encrypted_value(plaintext="boundary-secret", resource_id=resource_id)

    revealed = await module.reveal_sensitive_value(
        actor=make_user(GlobalRole.ANALYST),
        case_id=uuid4(),
        resource_type="evidence",
        resource_id=resource_id,
        field_name="source_locator",
        reason=reason,
        session=FakeSession(),
        context=make_context(
            provider=TrackingProvider(stored),
            crypto_service=crypto_service,
        ),
    )

    assert revealed == "boundary-secret"


@pytest.mark.asyncio
async def test_success_returns_plaintext_and_commits_plaintext_free_audit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Catches a reveal that omits its audit or copies the revealed value into durable metadata."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)
    plaintext = "https://private-source.example/path?token=secret"
    resource_id = "evidence-audited"
    stored, crypto_service = encrypted_value(plaintext=plaintext, resource_id=resource_id)
    session = FakeSession()

    revealed = await module.reveal_sensitive_value(
        actor=make_user(GlobalRole.CASE_OWNER),
        case_id=uuid4(),
        resource_type="evidence",
        resource_id=resource_id,
        field_name="source_locator",
        reason="  Verify source provenance for review  ",
        session=session,
        context=make_context(
            provider=TrackingProvider(stored),
            crypto_service=crypto_service,
            request_id="request-audited-reveal",
        ),
    )

    assert revealed == plaintext
    assert session.committed is True
    assert len(session.added) == 1
    event = session.added[0]
    assert isinstance(event, AuditEvent)
    assert event.event_type == "SENSITIVE_VALUE_REVEALED"
    assert event.resource_type == "evidence"
    assert event.resource_id == resource_id
    assert event.request_id == "request-audited-reveal"
    assert event.metadata_json == {
        "field_name": "source_locator",
        "reason": "Verify source provenance for review",
    }
    assert plaintext not in repr(event.__dict__)
    assert plaintext not in caplog.text


@pytest.mark.asyncio
async def test_failed_audit_commit_prevents_reveal_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches plaintext being returned before its reveal audit is durably committed."""
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(module, "authorize_case", authorize)
    plaintext = "commit-must-succeed-before-return"
    resource_id = "evidence-audit-failure"
    stored, crypto_service = encrypted_value(plaintext=plaintext, resource_id=resource_id)
    session = FakeSession(commit_error=RuntimeError("synthetic audit commit failure"))

    with pytest.raises(RuntimeError, match="synthetic audit commit failure"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.CASE_OWNER),
            case_id=uuid4(),
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Verify source provenance for review",
            session=session,
            context=make_context(
                provider=TrackingProvider(stored),
                crypto_service=crypto_service,
            ),
        )

    assert session.committed is False
