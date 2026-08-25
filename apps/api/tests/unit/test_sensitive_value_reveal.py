import importlib
import inspect
from typing import Any
from uuid import UUID, uuid4

import pytest
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.user import User
from darknetra_api.security.encryption import (
    SensitiveFieldCrypto,
    SensitiveFieldDecryptionError,
)


def reveal_module() -> Any:
    return importlib.import_module("darknetra_api.services.sensitive_values")


def make_user(*roles: GlobalRole) -> User:
    label = "-".join(role.value.casefold() for role in roles)
    return User(
        username=f"{label}-user",
        username_normalized=f"{label}-user",
        display_name=f"{label} User",
        password_hash="not-used",
        global_roles=list(roles),
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
        self.info: dict[str, object] = {}
        self.added: list[object] = []
        self.committed = False
        self.commit_error = commit_error

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True


class ScopedProvider:
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


class TrackingPermission:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls = 0

    async def __call__(self, **kwargs: object) -> bool:
        del kwargs
        self.calls += 1
        return self.result


class TrackingCrypto:
    def __init__(self, delegate: SensitiveFieldCrypto) -> None:
        self.delegate = delegate
        self.decrypt_calls = 0

    def decrypt(self, *args: object, **kwargs: object) -> str:
        self.decrypt_calls += 1
        return self.delegate.decrypt(*args, **kwargs)  # type: ignore[arg-type]


def encrypted_value(
    *,
    plaintext: str,
    resource_id: str,
    purpose: str = 'darknetra-sensitive-reveal:v1:["evidence","source_locator"]',
) -> tuple[object, SensitiveFieldCrypto]:
    module = reveal_module()
    crypto_service = crypto()
    envelope = crypto_service.encrypt(plaintext, purpose=purpose, resource_id=resource_id)
    return module.SensitiveValue(envelope=envelope), crypto_service


def bind_context(
    session: FakeSession,
    *,
    provider: ScopedProvider,
    permission: TrackingPermission | None = None,
    crypto_service: object | None = None,
    request_id: str = "request-sensitive-reveal",
) -> None:
    reveal_module().bind_sensitive_reveal_context(
        session,
        provider=provider,
        permission_predicate=permission or TrackingPermission(True),
        crypto=crypto_service or crypto(),
        request_id=request_id,
    )


def patch_case_authorization(
    monkeypatch: pytest.MonkeyPatch,
    *,
    effective_roles: set[GlobalRole],
) -> None:
    module = reveal_module()

    async def authorize(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def roles(*args: object, **kwargs: object) -> set[GlobalRole]:
        del args, kwargs
        return effective_roles

    monkeypatch.setattr(module, "authorize_case", authorize)
    monkeypatch.setattr(module, "_get_effective_case_roles", roles, raising=False)


def test_public_reveal_signature_has_exact_seven_keyword_only_arguments() -> None:
    """Catches dependency injection leaking into the public caller contract."""
    signature = inspect.signature(reveal_module().reveal_sensitive_value)

    assert list(signature.parameters) == [
        "actor",
        "case_id",
        "resource_type",
        "resource_id",
        "field_name",
        "reason",
        "session",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )


@pytest.mark.asyncio
async def test_mixed_global_roles_with_effective_viewer_membership_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches global ANALYST masking an effective VIEWER-only case membership."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.VIEWER})
    case_id = uuid4()
    resource_id = "evidence-effective-viewer"
    stored, crypto_service = encrypted_value(plaintext="viewer-secret", resource_id=resource_id)
    provider = ScopedProvider({(case_id, "evidence", resource_id, "source_locator"): stored})
    tracking_crypto = TrackingCrypto(crypto_service)
    session = FakeSession()
    bind_context(session, provider=provider, crypto_service=tracking_crypto)

    with pytest.raises(AuthorizationDenied, match="permission denied"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.VIEWER, GlobalRole.ANALYST),
            case_id=case_id,
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Investigating source provenance",
            session=session,
        )

    assert len(provider.calls) == 1
    assert tracking_crypto.decrypt_calls == 0
    assert session.added == []


@pytest.mark.asyncio
async def test_owning_feature_permission_denies_only_after_scoped_resource_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches resource policy running before case-scoped existence is established."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.ANALYST})
    case_id = uuid4()
    resource_id = "evidence-policy-denied"
    stored, crypto_service = encrypted_value(plaintext="policy-secret", resource_id=resource_id)
    provider = ScopedProvider({(case_id, "evidence", resource_id, "source_locator"): stored})
    permission = TrackingPermission(False)
    tracking_crypto = TrackingCrypto(crypto_service)
    session = FakeSession()
    bind_context(
        session,
        provider=provider,
        permission=permission,
        crypto_service=tracking_crypto,
    )

    with pytest.raises(AuthorizationDenied, match="permission denied"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=case_id,
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Investigating source provenance",
            session=session,
        )

    assert len(provider.calls) == 1
    assert permission.calls == 1
    assert tracking_crypto.decrypt_calls == 0


@pytest.mark.asyncio
async def test_inaccessible_and_unknown_cases_share_not_found_before_reason_or_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches validation or lookup leaking whether an inaccessible case exists."""
    module = reveal_module()
    provider = ScopedProvider({})
    session = FakeSession()
    bind_context(session, provider=provider)

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
                session=session,
            )
        outcomes.append((type(caught.value), caught.value.args))

    assert outcomes == [
        (CaseNotFound, ("resource not found",)),
        (CaseNotFound, ("resource not found",)),
    ]
    assert provider.calls == []


@pytest.mark.parametrize("reason", ["", " " * 20, "123456789", "x" * 501])
@pytest.mark.asyncio
async def test_reason_must_be_between_10_and_500_trimmed_characters(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Catches invalid justifications reaching scoped lookup or decryption."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.ANALYST})
    provider = ScopedProvider({})
    session = FakeSession()
    bind_context(session, provider=provider)

    with pytest.raises(module.SensitiveRevealReasonError, match="between 10 and 500 characters"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=uuid4(),
            resource_type="evidence",
            resource_id="evidence-invalid-reason",
            field_name="source_locator",
            reason=reason,
            session=session,
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_unknown_and_cross_case_resource_ids_share_not_found_before_predicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a cross-case scoped miss becoming a distinguishable permission denial."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.ANALYST})
    visible_case_id = uuid4()
    other_case_id = uuid4()
    cross_resource_id = "evidence-other-case"
    stored, _ = encrypted_value(plaintext="other-case-secret", resource_id=cross_resource_id)
    provider = ScopedProvider(
        {(other_case_id, "evidence", cross_resource_id, "source_locator"): stored}
    )
    permission = TrackingPermission(False)
    session = FakeSession()
    bind_context(session, provider=provider, permission=permission)

    outcomes: list[tuple[type[BaseException], tuple[object, ...]]] = []
    for resource_id in (cross_resource_id, "evidence-unknown"):
        with pytest.raises(CaseNotFound) as caught:
            await module.reveal_sensitive_value(
                actor=make_user(GlobalRole.ANALYST),
                case_id=visible_case_id,
                resource_type="evidence",
                resource_id=resource_id,
                field_name="source_locator",
                reason="Investigating source provenance",
                session=session,
            )
        outcomes.append((type(caught.value), caught.value.args))

    assert outcomes == [
        (CaseNotFound, ("resource not found",)),
        (CaseNotFound, ("resource not found",)),
    ]
    assert permission.calls == 0


@pytest.mark.asyncio
async def test_requested_field_derives_purpose_independently_of_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches provider confusion decrypting field B while authorizing and auditing field A."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.ANALYST})
    case_id = uuid4()
    resource_id = "evidence-purpose-confusion"
    stored, crypto_service = encrypted_value(
        plaintext="custody-secret",
        resource_id=resource_id,
        purpose='darknetra-sensitive-reveal:v1:["evidence","custody_notes"]',
    )
    provider = ScopedProvider({(case_id, "evidence", resource_id, "source_locator"): stored})
    session = FakeSession()
    bind_context(session, provider=provider, crypto_service=crypto_service)

    with pytest.raises(SensitiveFieldDecryptionError, match="decryption failed"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=case_id,
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Investigating source provenance",
            session=session,
        )

    assert session.added == []
    assert session.committed is False


@pytest.mark.asyncio
async def test_reveal_rejects_dot_ambiguous_resource_and_field_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches dotted purpose composition authenticating a different resource/field tuple."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.ANALYST})
    case_id = uuid4()
    resource_id = "evidence-dot-purpose-confusion"
    stored, crypto_service = encrypted_value(
        plaintext="dot-ambiguous-secret",
        resource_id=resource_id,
        purpose='darknetra-sensitive-reveal:v1:["evidence.source","locator"]',
    )
    provider = ScopedProvider(
        {(case_id, "evidence", resource_id, "source.locator"): stored}
    )
    session = FakeSession()
    bind_context(session, provider=provider, crypto_service=crypto_service)

    with pytest.raises(SensitiveFieldDecryptionError, match="decryption failed"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.ANALYST),
            case_id=case_id,
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source.locator",
            reason="Investigating source provenance",
            session=session,
        )

    assert session.added == []
    assert session.committed is False


@pytest.mark.parametrize("reason", ["x" * 10, "x" * 500])
@pytest.mark.asyncio
async def test_reason_accepts_inclusive_policy_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Catches exclusive-bound validation rejecting a policy-valid reveal reason."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.ANALYST})
    case_id = uuid4()
    resource_id = "evidence-reason-boundary"
    stored, crypto_service = encrypted_value(plaintext="boundary-secret", resource_id=resource_id)
    provider = ScopedProvider({(case_id, "evidence", resource_id, "source_locator"): stored})
    session = FakeSession()
    bind_context(session, provider=provider, crypto_service=crypto_service)

    revealed = await module.reveal_sensitive_value(
        actor=make_user(GlobalRole.ANALYST),
        case_id=case_id,
        resource_type="evidence",
        resource_id=resource_id,
        field_name="source_locator",
        reason=reason,
        session=session,
    )

    assert revealed == "boundary-secret"


@pytest.mark.asyncio
async def test_exact_seven_argument_call_returns_plaintext_and_commits_safe_audit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Catches a reveal requiring extra arguments or persisting plaintext in its audit."""
    module = reveal_module()
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.CASE_OWNER})
    plaintext = "https://private-source.example/path?token=secret"
    case_id = uuid4()
    resource_id = "evidence-audited"
    stored, crypto_service = encrypted_value(plaintext=plaintext, resource_id=resource_id)
    provider = ScopedProvider({(case_id, "evidence", resource_id, "source_locator"): stored})
    session = FakeSession()
    bind_context(
        session,
        provider=provider,
        crypto_service=crypto_service,
        request_id="request-audited-reveal",
    )

    revealed = await module.reveal_sensitive_value(
        actor=make_user(GlobalRole.CASE_OWNER),
        case_id=case_id,
        resource_type="evidence",
        resource_id=resource_id,
        field_name="source_locator",
        reason="  Verify source provenance for review  ",
        session=session,
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
    patch_case_authorization(monkeypatch, effective_roles={GlobalRole.CASE_OWNER})
    plaintext = "commit-must-succeed-before-return"
    case_id = uuid4()
    resource_id = "evidence-audit-failure"
    stored, crypto_service = encrypted_value(plaintext=plaintext, resource_id=resource_id)
    provider = ScopedProvider({(case_id, "evidence", resource_id, "source_locator"): stored})
    session = FakeSession(commit_error=RuntimeError("synthetic audit commit failure"))
    bind_context(session, provider=provider, crypto_service=crypto_service)

    with pytest.raises(RuntimeError, match="synthetic audit commit failure"):
        await module.reveal_sensitive_value(
            actor=make_user(GlobalRole.CASE_OWNER),
            case_id=case_id,
            resource_type="evidence",
            resource_id=resource_id,
            field_name="source_locator",
            reason="Verify source provenance for review",
            session=session,
        )

    assert session.committed is False
