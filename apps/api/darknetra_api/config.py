from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    build_version: str = "dev"
    database_url: str = (
        "postgresql+psycopg://darknetra:darknetra-dev-only@127.0.0.1:5432/darknetra"
    )

    model_config = SettingsConfigDict(env_prefix="DARKNETRA_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
