from __future__ import annotations

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    directory_url: AnyHttpUrl = "http://localhost:8000"
    service_url: AnyHttpUrl | None = None
    log_level: str = "INFO"

    premium_payment_token: str | None = None

    # Zynd Naming Service display identity. Agents still keep their signed
    # cryptographic IDs, but logs/UI use the FQAN for human-readable routing.
    zns_root: str = "zns01.zynd.ai"
    zns_developer_handle: str = "venture-swarm"

    # Optional x402 / Base Sepolia showcase. The SDK derives the EVM wallet from
    # the agent Ed25519 identity; these values only select the payment network.
    x402_enabled: bool = False
    x402_network: str = "eip155:84532"
    x402_network_name: str = "Base Sepolia"
    x402_usdc_asset: str = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_sync_facilitator_on_start: bool = True

    # LLM provider configuration. Leave LLM_PROVIDER unset/none to keep agents in
    # no-data mode; set it with the matching API key for live reasoning.
    llm_provider: str = "none"
    llm_timeout_s: float = 20.0
    llm_max_items: int = 5

    # Optional real web-data grounding. When enabled, agents fetch Apify context
    # before asking the configured LLM to structure/analyze the result.
    apify_enabled: bool = False
    apify_api_token: str | None = None
    apify_max_items: int = 5
    apify_timeout_s: int = 20
    apify_cache_ttl_s: int = 600
    apify_google_search_actor: str = "apify/google-search-scraper"
    apify_google_news_actor: str = "apify/google-news-scraper"
    apify_reddit_actor: str = "trudax/reddit-scraper"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"

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
