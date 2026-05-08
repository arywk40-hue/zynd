from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import PublicFormat
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

from shared.config import Settings
from shared.schemas import AgentCard, HeartbeatRequest, RegisterAgentRequest, SearchAgentsResponse
from shared.utils import get_logger, http_client, sleep_jitter


log = get_logger("ZyndSDK")


def _load_or_create_ed25519_key(key_path: str | None) -> Ed25519PrivateKey:
    if not key_path:
        return Ed25519PrivateKey.generate()

    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            raw = f.read()
        return Ed25519PrivateKey.from_private_bytes(raw)

    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    with open(key_path, "wb") as f:
        f.write(raw)
    return key


def _agent_id_from_key(key: Ed25519PrivateKey) -> str:
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.urlsafe_b64encode(pub).decode("utf-8").rstrip("=")


@dataclass(frozen=True)
class ZyndClient:
    settings: Settings

    def _base(self) -> str:
        return str(self.settings.directory_url).rstrip("/")

    async def register_agent(self, card: AgentCard, ttl_s: float) -> None:
        payload = RegisterAgentRequest(card=card, ttl_s=ttl_s).model_dump(mode="json")
        async with http_client() as client:
            r = await client.post(f"{self._base()}/register", json=payload)
            r.raise_for_status()

    async def search_agents(self, keyword: str) -> list[AgentCard]:
        async with http_client() as client:
            r = await client.get(f"{self._base()}/search", params={"keyword": keyword})
            r.raise_for_status()
            parsed = SearchAgentsResponse.model_validate(r.json())
            return parsed.agents

    async def heartbeat(self, agent_id: str) -> None:
        async with http_client() as client:
            r = await client.post(
                f"{self._base()}/heartbeat",
                json=HeartbeatRequest(agent_id=agent_id).model_dump(mode="json"),
            )
            r.raise_for_status()


class ZyndAIAgent:
    def __init__(
        self,
        *,
        settings: Settings,
        name: str,
        description: str,
        capabilities: list[str],
        tags: list[str],
        webhook_sync_url: str,
        health_url: str,
        premium_required: bool = False,
        premium_cost_usd: float | None = None,
        initial_reputation: dict[str, Any] | None = None,
        key_path: str | None = None,
    ) -> None:
        self._settings = settings
        self._client = ZyndClient(settings=settings)
        self._key = _load_or_create_ed25519_key(key_path)
        self.agent_id = _agent_id_from_key(self._key)
        self._task: asyncio.Task[None] | None = None

        reputation = initial_reputation or {}
        self.card = AgentCard(
            agent_id=self.agent_id,
            name=name,
            description=description,
            capabilities=capabilities,
            tags=tags,
            webhook_sync_url=webhook_sync_url,
            health_url=health_url,
            reputation=reputation,  # pydantic will coerce into AgentReputation
            premium_required=premium_required,
            premium_cost_usd=premium_cost_usd,
        )

    async def start(self) -> None:
        log.info("[Registration] Registering [bold]%s[/bold] (%s) ...", self.card.name, self.agent_id)
        await self._client.register_agent(self.card, ttl_s=self._settings.agent_ttl_s)
        self._task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await sleep_jitter(self._settings.heartbeat_interval_s)
                await self._client.heartbeat(self.agent_id)
            except Exception as e:  # noqa: BLE001
                log.warning("[Heartbeat] %s heartbeat failed: %s", self.card.name, e)


def signed_payload(agent: ZyndAIAgent, payload: dict[str, Any]) -> dict[str, Any]:
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = agent._key.sign(message)  # noqa: SLF001
    return {"payload": payload, "signature_b64": base64.b64encode(sig).decode("utf-8")}
