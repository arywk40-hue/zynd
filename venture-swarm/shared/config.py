from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    directory_url: AnyHttpUrl = "http://localhost:8000"
    service_url: AnyHttpUrl | None = None
    log_level: str = "INFO"

    premium_payment_token: str | None = None

    # LLM provider configuration. Leave LLM_PROVIDER unset/none to keep agents in
    # no-data mode; set it with the matching API key for live reasoning.
    llm_provider: str = "none"
    llm_timeout_s: float = 20.0
    llm_max_items: int = 5

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-haiku-latest"

    mistral_api_key: str | None = None
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_model: str = "mistral-small-latest"

    cerebras_api_key: str | None = None
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_model: str = "llama3.1-8b"

    # SDK registry compatibility
    zynd_registry_url: AnyHttpUrl | None = None

    # SDK webhook sidecar ports (FastAPI uses service ports, SDK uses sidecar webhook ports)
    orchestrator_sdk_webhook_port: int = 9201


def get_settings() -> Settings:
    return Settings()
