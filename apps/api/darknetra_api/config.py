from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"
    build_version: str = "dev"

    model_config = SettingsConfigDict(env_prefix="DARKNETRA_", extra="ignore")


def get_settings() -> Settings:
    return Settings()
