import base64

from darknetra_api.config import Settings


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
