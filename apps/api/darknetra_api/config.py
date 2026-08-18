from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    build_version: str = "dev"
    redis_url: str = "redis://127.0.0.1:6379/0"
    database_url: str = (
        "postgresql+psycopg://darknetra:darknetra-dev-only@127.0.0.1:5432/darknetra"
    )
    web_origin: str = "http://localhost:3000"
    jwt_signing_key_b64: str = ""
    field_key_v1_b64: str = ""
    field_keyring_b64_json: str = ""
    field_blind_index_key_b64: str = ""
    field_active_key_version: str = "v1"

    model_config = SettingsConfigDict(env_prefix="DARKNETRA_", extra="ignore")

    @property
    def auth_cookie_secure(self) -> bool:
        local_http_origins = {"http://localhost:3000", "http://127.0.0.1:3000"}
        return not (self.environment == "development" and self.web_origin in local_http_origins)

    def require_jwt_signing_key_b64(self) -> str:
        if not self.jwt_signing_key_b64:
            raise RuntimeError("DARKNETRA_JWT_SIGNING_KEY_B64 must be configured")
        return self.jwt_signing_key_b64

    def require_field_key_v1_b64(self) -> str:
        if not self.field_key_v1_b64:
            raise RuntimeError("DARKNETRA_FIELD_KEY_V1_B64 must be configured")
        return self.field_key_v1_b64

    def require_field_blind_index_key_b64(self) -> str:
        if not self.field_blind_index_key_b64:
            raise RuntimeError("DARKNETRA_FIELD_BLIND_INDEX_KEY_B64 must be configured")
        return self.field_blind_index_key_b64


@lru_cache
def get_settings() -> Settings:
    return Settings()
