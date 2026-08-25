import base64

import pytest
from darknetra_api.config import Settings
from darknetra_api.security.encryption import SensitiveFieldConfigurationError
from pydantic import ValidationError


def encoded_key(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode("ascii")


def test_sensitive_field_settings_load_from_explicit_environment_variables(
    monkeypatch,
) -> None:
    field_key = encoded_key(0x11)
    blind_index_key = encoded_key(0x22)
    monkeypatch.setenv("DARKNETRA_FIELD_KEY_V1_B64", field_key)
    monkeypatch.setenv("DARKNETRA_FIELD_BLIND_INDEX_KEY_B64", blind_index_key)
    monkeypatch.setenv("DARKNETRA_FIELD_ACTIVE_KEY_VERSION", "v7")

    settings = Settings(_env_file=None)

    assert settings.field_key_v1_b64 == field_key
    assert settings.field_blind_index_key_b64 == blind_index_key
    assert settings.field_active_key_version == "v7"


def test_sensitive_field_active_key_version_defaults_to_v1() -> None:
    assert Settings(_env_file=None).field_active_key_version == "v1"


def test_sensitive_field_keys_are_redacted_from_settings_repr() -> None:
    field_key = encoded_key(0x33)
    blind_index_key = encoded_key(0x44)

    rendered = repr(
        Settings(
            field_key_v1_b64=field_key,
            field_blind_index_key_b64=blind_index_key,
            _env_file=None,
        )
    )

    assert field_key not in rendered
    assert blind_index_key not in rendered


@pytest.mark.parametrize(
    "field_name",
    ["field_key_v1_b64", "field_blind_index_key_b64"],
)
def test_sensitive_field_settings_reject_keys_that_are_not_32_bytes(field_name: str) -> None:
    with pytest.raises(ValidationError, match="exactly 32 bytes"):
        Settings(**{field_name: base64.b64encode(b"short").decode("ascii")}, _env_file=None)


@pytest.mark.parametrize(
    "field_name",
    ["field_key_v1_b64", "field_blind_index_key_b64"],
)
def test_sensitive_field_settings_reject_malformed_base64(field_name: str) -> None:
    with pytest.raises(ValidationError, match="valid base64"):
        Settings(**{field_name: "not base64!"}, _env_file=None)


def test_sensitive_field_validation_errors_do_not_expose_key_material() -> None:
    rejected_key = base64.b64encode(b"sensitive-but-short").decode("ascii")

    with pytest.raises(ValidationError) as caught:
        Settings(field_key_v1_b64=rejected_key, _env_file=None)

    assert rejected_key not in str(caught.value)
    assert rejected_key not in repr(caught.value)


def test_sensitive_field_crypto_factory_decodes_runtime_settings() -> None:
    service = Settings(
        field_key_v1_b64=encoded_key(0x11),
        field_blind_index_key_b64=encoded_key(0x22),
        _env_file=None,
    ).require_sensitive_field_crypto()

    encrypted = service.encrypt(
        "factory secret",
        purpose="custody.notes",
        resource_id="record-a",
    )

    assert (
        service.decrypt(
            encrypted,
            purpose="custody.notes",
            resource_id="record-a",
        )
        == "factory secret"
    )


@pytest.mark.parametrize(
    ("configured_key", "missing_variable"),
    [
        ({"field_key_v1_b64": encoded_key(0x11)}, "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64"),
        (
            {"field_blind_index_key_b64": encoded_key(0x22)},
            "DARKNETRA_FIELD_KEY_V1_B64",
        ),
    ],
)
def test_sensitive_field_crypto_factory_requires_both_runtime_keys(
    configured_key: dict[str, str],
    missing_variable: str,
) -> None:
    settings = Settings(**configured_key, _env_file=None)

    with pytest.raises(
        SensitiveFieldConfigurationError,
        match=rf"{missing_variable} must be configured",
    ):
        settings.require_sensitive_field_crypto()
