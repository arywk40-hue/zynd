from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    directory_url: AnyHttpUrl = "http://localhost:8000"
    service_url: AnyHttpUrl | None = None
    log_level: str = "INFO"

    premium_payment_token: str | None = None

    # SDK registry compatibility
    zynd_registry_url: AnyHttpUrl | None = None

    # SDK webhook sidecar ports (FastAPI uses service ports, SDK uses sidecar webhook ports)
    orchestrator_sdk_webhook_port: int = 9201


def get_settings() -> Settings:
    return Settings()
