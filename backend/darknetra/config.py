"""Validated application settings; importing this module reads no secrets."""

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DARKNETRA_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    env: Literal["development", "test", "production"] = "development"
    build_version: str = "dev"
    database_url: str = Field(repr=False)
    migration_database_url: str | None = Field(None, repr=False)
    test_database_url: str | None = Field(None, repr=False)
    vault_path: Path = Path("./vault")
    web_origin: str = "http://localhost:3000"
    jwt_signing_key_b64: SecretStr
    field_key_b64: SecretStr
    access_ttl_seconds: int = Field(900, gt=0)
    refresh_ttl_seconds: int = Field(28800, gt=0)
    max_upload_bytes: int = Field(200 * 1024 * 1024, gt=0)
    max_zip_bytes: int = Field(500 * 1024 * 1024, gt=0)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: Literal[1024] = 1024
    embedding_backend: Literal["none", "sentence_transformers"] = "none"
    embedding_model_path: Path | None = None
    embedding_batch_size: int = Field(32, ge=1, le=256)
    embedding_timeout_seconds: float = Field(60, gt=0, le=600)
    offline_mode: bool = False
    demo_mode: bool = False
    scheduler_enabled: bool = True
    triage_model_enabled: bool = False
    apify_telegram_actor: str | None = None
    monitor_interval_override: int | None = Field(None, gt=0)
    harness_mode: Literal["auto", "offline", "deterministic", "nim"] = "auto"
    anthropic_api_key: SecretStr | None = None
    anthropic_api_key_backup: SecretStr | None = None
    case_lead_model: str = "claude-opus-5"
    worker_model: str = "claude-sonnet-5"
    nim_base_url: str | None = None
    nim_api_key: SecretStr | None = None
    nim_model: str | None = None
    nim_worker_model: str | None = None
    nim_timeout_seconds: float = Field(120, gt=0, le=600)
    nim_max_tokens: int = Field(4096, ge=1, le=65536)
    nim_input_cost_per_million: float | None = Field(None, ge=0, allow_inf_nan=False)
    nim_output_cost_per_million: float | None = Field(None, ge=0, allow_inf_nan=False)
    ollama_url: str = "http://127.0.0.1:11434"
    offline_model: str = "qwen3:8b"
    tavily_api_key: SecretStr | None = None
    chainalysis_api_key: SecretStr | None = None
    trongrid_api_key: SecretStr | None = None
    etherscan_api_key: SecretStr | None = None
    apify_token: SecretStr | None = None
    mcp_gateway_url: str | None = None
    tor_socks_url: str | None = None
    surface_search_searxng_url: str | None = None
    log_level: str = "INFO"

    @field_validator(
        "migration_database_url",
        "test_database_url",
        "monitor_interval_override",
        "embedding_model_path",
        "anthropic_api_key",
        "anthropic_api_key_backup",
        "nim_base_url",
        "nim_api_key",
        "nim_model",
        "nim_worker_model",
        "nim_input_cost_per_million",
        "nim_output_cost_per_million",
        "tavily_api_key",
        "chainalysis_api_key",
        "trongrid_api_key",
        "etherscan_api_key",
        "apify_token",
        "apify_telegram_actor",
        "mcp_gateway_url",
        "tor_socks_url",
        "surface_search_searxng_url",
        mode="before",
    )
    @classmethod
    def empty_optional_url(cls, value: Any) -> Any:
        return None if value is None or value == "" else value

    @field_validator("jwt_signing_key_b64", "field_key_b64")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        try:
            decoded = base64.b64decode(value.get_secret_value(), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("key must be valid base64 encoding 32 bytes") from None
        if len(decoded) != 32:
            raise ValueError("key must encode exactly 32 bytes")
        return value

    @property
    def jwt_signing_key(self) -> bytes:
        return base64.b64decode(self.jwt_signing_key_b64.get_secret_value())

    @property
    def field_key(self) -> bytes:
        return base64.b64decode(self.field_key_b64.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
