from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    directory_url: AnyHttpUrl = "http://localhost:8000"
    service_url: AnyHttpUrl | None = None
    log_level: str = "INFO"

    premium_payment_token: str | None = None

    # Agent registration/heartbeat
    heartbeat_interval_s: float = 5.0
    agent_ttl_s: float = 30.0


def get_settings() -> Settings:
    return Settings()

