import base64
import json
from pathlib import Path

import pytest
from darknetra_api.config import Settings
from darknetra_api.security.encryption import (
    SensitiveFieldConfigurationError,
    SensitiveFieldCrypto,
)
from pydantic import ValidationError


def encoded_key(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode("ascii")


def equivalent_noncanonical_encoding(encoded: str) -> str:
    base64_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    final_character = base64_alphabet.index(encoded[-2])
    alternate = encoded[:-2] + base64_alphabet[final_character ^ 0x01] + encoded[-1]
    assert alternate != encoded
    assert base64.b64decode(alternate, validate=True) == base64.b64decode(
        encoded,
        validate=True,
    )
    return alternate


def test_sensitive_field_settings_load_from_explicit_environment_variables(
    monkeypatch,
) -> None:
    field_key = encoded_key(0x11)
    keyring = json.dumps({"v1": field_key, "v2": encoded_key(0x33)})
    blind_index_key = encoded_key(0x22)
    monkeypatch.setenv("DARKNETRA_FIELD_KEY_V1_B64", field_key)
    monkeypatch.setenv("DARKNETRA_FIELD_KEYRING_B64_JSON", keyring)
    monkeypatch.setenv("DARKNETRA_FIELD_BLIND_INDEX_KEY_B64", blind_index_key)
    monkeypatch.setenv("DARKNETRA_FIELD_ACTIVE_KEY_VERSION", "v7")

    settings = Settings(_env_file=None)

    assert settings.field_key_v1_b64 == field_key
    assert settings.field_keyring_b64_json == keyring
    assert settings.field_blind_index_key_b64 == blind_index_key
    assert settings.field_active_key_version == "v7"


def test_sensitive_field_active_key_version_defaults_to_v1() -> None:
    assert Settings(_env_file=None).field_active_key_version == "v1"


def test_database_owner_url_is_distinct_and_optional_for_runtime_startup() -> None:
    runtime_url = "postgresql+psycopg://runtime:secret@db:5432/darknetra"
    owner_url = "postgresql+psycopg://owner:secret@db:5432/darknetra"
    settings = Settings(
        database_url=runtime_url,
        database_owner_url=owner_url,
        _env_file=None,
    )

    assert settings.database_url == runtime_url
    assert settings.database_owner_url == owner_url


def test_sensitive_field_keys_are_redacted_from_settings_repr() -> None:
    field_key = encoded_key(0x33)
    keyring = json.dumps({"v1": field_key, "v2": encoded_key(0x55)})
    blind_index_key = encoded_key(0x44)

    rendered = repr(
        Settings(
            field_key_v1_b64=field_key,
            field_keyring_b64_json=keyring,
            field_blind_index_key_b64=blind_index_key,
            _env_file=None,
        )
    )

    assert field_key not in rendered
    assert keyring not in rendered
    assert blind_index_key not in rendered


def test_database_credentials_are_redacted_from_settings_repr() -> None:
    runtime_password = "runtime-password-must-not-leak"
    owner_password = "owner-password-must-not-leak"
    rendered = repr(
        Settings(
            database_url=(
                f"postgresql+psycopg://runtime:{runtime_password}@db:5432/darknetra"
            ),
            database_owner_url=(
                f"postgresql+psycopg://owner:{owner_password}@db:5432/darknetra"
            ),
            _env_file=None,
        )
    )

    assert runtime_password not in rendered
    assert owner_password not in rendered


def test_evidence_store_path_is_redacted_and_trusted_fallback_defaults_off() -> None:
    sensitive_path = Path("/internal/evidence/store/location")
    settings = Settings(evidence_store_root=sensitive_path, _env_file=None)

    assert str(sensitive_path) not in repr(settings)
    assert settings.evidence_store_allow_trusted_volume_fallback is False


def test_evidence_upload_limit_defaults_to_100_mib_and_has_a_500_mib_ceiling() -> None:
    settings = Settings(_env_file=None)

    assert settings.evidence_upload_max_bytes == 100 * 1024 * 1024
    assert Settings(evidence_upload_max_bytes=500 * 1024 * 1024, _env_file=None)
    with pytest.raises(ValueError):
        Settings(evidence_upload_max_bytes=0, _env_file=None)
    with pytest.raises(ValueError):
        Settings(evidence_upload_max_bytes=500 * 1024 * 1024 + 1, _env_file=None)


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


def test_sensitive_field_crypto_factory_supports_multiple_key_versions() -> None:
    settings = Settings(
        field_keyring_b64_json=json.dumps(
            {"v1": encoded_key(0x11), "v2": encoded_key(0x33)}
        ),
        field_active_key_version="v2",
        field_blind_index_key_b64=encoded_key(0x22),
        _env_file=None,
    )
    v1_crypto = SensitiveFieldCrypto(
        field_keys={"v1": bytes([0x11]) * 32},
        active_key_version="v1",
        blind_index_key=bytes([0x22]) * 32,
    )
    old_value = v1_crypto.encrypt(
        "old secret",
        purpose="custody.notes",
        resource_id="record-a",
    )

    service = settings.require_sensitive_field_crypto()
    new_value = service.encrypt(
        "new secret",
        purpose="custody.notes",
        resource_id="record-b",
    )

    assert new_value.key_version == "v2"
    assert (
        service.decrypt(old_value, purpose="custody.notes", resource_id="record-a")
        == "old secret"
    )


def test_sensitive_field_crypto_factory_rejects_unconfigured_active_version() -> None:
    settings = Settings(
        field_keyring_b64_json=json.dumps({"v1": encoded_key(0x11)}),
        field_active_key_version="v2",
        field_blind_index_key_b64=encoded_key(0x22),
        _env_file=None,
    )

    with pytest.raises(
        SensitiveFieldConfigurationError,
        match="active field key version is not configured",
    ):
        settings.require_sensitive_field_crypto()


def test_sensitive_field_settings_reject_invalid_versioned_key_material() -> None:
    rejected_key = base64.b64encode(b"sensitive-but-short").decode("ascii")

    with pytest.raises(ValidationError) as caught:
        Settings(
            field_keyring_b64_json=json.dumps({"v2": rejected_key}),
            _env_file=None,
        ).require_sensitive_field_crypto()

    assert "exactly 32 bytes" in str(caught.value)
    assert rejected_key not in str(caught.value)


def test_sensitive_field_factory_rejects_duplicate_decoded_key_material() -> None:
    reused_key = encoded_key(0x71)
    alternate_encoding = equivalent_noncanonical_encoding(reused_key)
    settings = Settings(
        field_keyring_b64_json=json.dumps(
            {"v1": reused_key, "v2": alternate_encoding}
        ),
        field_active_key_version="v2",
        field_blind_index_key_b64=encoded_key(0x72),
        _env_file=None,
    )

    with pytest.raises(
        SensitiveFieldConfigurationError,
        match="field encryption keys must use distinct key material",
    ) as caught:
        settings.require_sensitive_field_crypto()

    assert reused_key not in str(caught.value)
    assert reused_key not in repr(caught.value)
    assert alternate_encoding not in str(caught.value)
    assert alternate_encoding not in repr(caught.value)


def test_legacy_and_json_v1_compare_decoded_key_bytes() -> None:
    """Catches equivalent Base64 spellings being rejected as conflicting v1 key sources."""
    legacy_v1 = encoded_key(0x73)
    json_v1 = equivalent_noncanonical_encoding(legacy_v1)
    settings = Settings(
        field_key_v1_b64=legacy_v1,
        field_keyring_b64_json=json.dumps({"v1": json_v1}),
        field_blind_index_key_b64=encoded_key(0x74),
        _env_file=None,
    )

    service = settings.require_sensitive_field_crypto()

    assert service.key_versions == frozenset({"v1"})


def test_sensitive_field_settings_reject_duplicate_json_version_members() -> None:
    first_key = encoded_key(0x81)
    second_key = encoded_key(0x82)
    duplicate_members = f'{{"v1":"{first_key}","v1":"{second_key}"}}'

    with pytest.raises(ValidationError, match="duplicate key version") as caught:
        Settings(field_keyring_b64_json=duplicate_members, _env_file=None)

    assert first_key not in str(caught.value)
    assert second_key not in str(caught.value)


@pytest.mark.parametrize(
    ("configured_key", "missing_configuration"),
    [
        ({"field_key_v1_b64": encoded_key(0x11)}, "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64"),
        (
            {"field_blind_index_key_b64": encoded_key(0x22)},
            "DARKNETRA_FIELD_KEYRING_B64_JSON or DARKNETRA_FIELD_KEY_V1_B64",
        ),
    ],
)
def test_sensitive_field_crypto_factory_requires_both_runtime_keys(
    configured_key: dict[str, str],
    missing_configuration: str,
) -> None:
    settings = Settings(**configured_key, _env_file=None)

    with pytest.raises(
        SensitiveFieldConfigurationError,
        match=rf"{missing_configuration} must be configured",
    ):
        settings.require_sensitive_field_crypto()
