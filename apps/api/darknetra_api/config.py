from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from darknetra_api.security.encryption import (
    SensitiveFieldCrypto,
    decode_key_b64,
)
from darknetra_api.security.key_versions import validate_key_version
from darknetra_api.security.keyring import SensitiveFieldKeyring, validate_keyring_b64_json

_FIELD_KEY_V1_VARIABLE = "DARKNETRA_FIELD_KEY_V1_B64"
_BLIND_INDEX_KEY_VARIABLE = "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64"


class Settings(BaseSettings):
    environment: str = "development"
    build_version: str = "dev"
    database_url: str = (
        "postgresql+psycopg://darknetra:darknetra-dev-only@127.0.0.1:5432/darknetra"
    )
    web_origin: str = "http://localhost:3000"
    jwt_signing_key_b64: str = ""
    field_key_v1_b64: str = Field(default="", repr=False)
    field_keyring_b64_json: str = Field(default="", repr=False)
    field_blind_index_key_b64: str = Field(default="", repr=False)
    field_active_key_version: str = "v1"

    model_config = SettingsConfigDict(
        env_prefix="DARKNETRA_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @property
    def auth_cookie_secure(self) -> bool:
        local_http_origins = {"http://localhost:3000", "http://127.0.0.1:3000"}
        return not (self.environment == "development" and self.web_origin in local_http_origins)

    def require_jwt_signing_key_b64(self) -> str:
        if not self.jwt_signing_key_b64:
            raise RuntimeError("DARKNETRA_JWT_SIGNING_KEY_B64 must be configured")
        return self.jwt_signing_key_b64

    def require_sensitive_field_crypto(self) -> SensitiveFieldCrypto:
        return SensitiveFieldKeyring.from_settings(self).crypto()

    @field_validator("field_key_v1_b64")
    @classmethod
    def validate_field_key_v1_b64(cls, value: str) -> str:
        if value:
            decode_key_b64(value, variable=_FIELD_KEY_V1_VARIABLE)
        return value

    @field_validator("field_keyring_b64_json")
    @classmethod
    def validate_field_keyring_b64_json(cls, value: str) -> str:
        if value:
            validate_keyring_b64_json(value)
        return value

    @field_validator("field_blind_index_key_b64")
    @classmethod
    def validate_field_blind_index_key_b64(cls, value: str) -> str:
        if value:
            decode_key_b64(value, variable=_BLIND_INDEX_KEY_VARIABLE)
        return value

    @field_validator("field_active_key_version")
    @classmethod
    def validate_field_active_key_version(cls, value: str) -> str:
        return validate_key_version(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
