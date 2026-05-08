from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import signature
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import BackgroundTasks, HTTPException
from zyndai_agent import dns_registry
from zyndai_agent.agent import AgentConfig, ZyndAIAgent
from zyndai_agent.base import SkillConfig
from zyndai_agent.ed25519_identity import generate_keypair, save_keypair, sign
from zyndai_agent.message import AgentMessage

from shared.config import Settings
from shared.schemas import AgentTaskResponse, CandidateAgent
from shared.utils import get_logger


log = get_logger("ZyndRuntime")


def ensure_sdk_keypair(path: str) -> str:
    key_path = Path(path)
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        save_keypair(generate_keypair(), str(key_path))
    return str(key_path)


def ensure_local_developer_keypair() -> None:
    if os.environ.get("ZYND_DEVELOPER_KEYPAIR_PATH"):
        return
    os.environ["ZYND_DEVELOPER_KEYPAIR_PATH"] = ensure_sdk_keypair(".keys/developer.json")


def _skills_from_config(config: dict[str, Any]) -> list[SkillConfig]:
    skill_names = list((config.get("capabilities") or {}).get("skills") or [])
    return [
        SkillConfig(
            id=skill,
            name=skill,
            description=f"{skill} capability",
            tags=[skill],
        )
        for skill in skill_names
    ]


def build_sdk_agent(
    *,
    settings: Settings,
    config: dict[str, Any],
    service_url: str,
    default_name: str,
    default_description: str,
    default_port: int,
    config_dir: str,
    price: str | None = None,
) -> ZyndAIAgent:
    ensure_local_developer_keypair()

    name = config.get("name", default_name)
    keypair_path = os.environ.get("ZYND_AGENT_KEYPAIR_PATH") or ensure_sdk_keypair(f".keys/{name}.json")
    registry_url = str(settings.zynd_registry_url or settings.directory_url).rstrip("/")

    agent_config = AgentConfig(
        name=name,
        description=config.get("description", default_description),
        category=config.get("category", "startup-intelligence"),
        tags=config.get("tags", []),
        registry_url=registry_url,
        entity_url=service_url.rstrip("/"),
        server_port=int(config.get("webhook_port", default_port)),
        keypair_path=keypair_path,
        config_dir=config_dir,
        card_output=f"{config_dir}/agent-card.json",
        skills=_skills_from_config(config),
        price=price,
    )
    return ZyndAIAgent(agent_config)


def start_sdk_runtime(agent: ZyndAIAgent) -> None:
    runner = getattr(agent, "run", None) or getattr(agent, "start")
    runner()


def stop_sdk_runtime(agent: ZyndAIAgent) -> None:
    stopper = getattr(agent, "stop_heartbeat", None) or getattr(agent, "stop", None)
    if stopper:
        stopper()


def sdk_agent_id(agent: ZyndAIAgent | None) -> str | None:
    if agent is None:
        return None
    return str(getattr(agent, "agent_id", None) or getattr(agent, "entity_id", None))


def heartbeat_connected(agent: ZyndAIAgent | None) -> bool:
    if agent is None:
        return False

    heartbeat_client = getattr(agent, "heartbeat_client", None)
    if heartbeat_client is not None and hasattr(heartbeat_client, "is_connected"):
        return bool(heartbeat_client.is_connected())

    heartbeat_thread = getattr(agent, "_heartbeat_thread", None)
    heartbeat_stop = getattr(agent, "_heartbeat_stop", None)
    return bool(
        heartbeat_thread is not None
        and heartbeat_thread.is_alive()
        and not (heartbeat_stop is not None and heartbeat_stop.is_set())
    )


def sdk_agent_card(agent: ZyndAIAgent | None) -> dict[str, Any]:
    if agent is None:
        raise HTTPException(status_code=503, detail="agent runtime is not ready")

    base_url = str(agent.agent_config.entity_url or "").rstrip("/")
    skills = [skill.id for skill in (agent.agent_config.skills or [])]
    pricing = _pricing_from_agent(agent)

    card: dict[str, Any] = {
        "agent_id": sdk_agent_id(agent),
        "public_key": agent.keypair.public_key_b64,
        "name": agent.agent_config.name,
        "description": agent.agent_config.description,
        "category": agent.agent_config.category,
        "tags": agent.agent_config.tags or [],
        "capabilities": skills,
        "protocols": ["webhook", "webhook-sync", "agent-card"],
        "supported_models": [],
        "endpoints": {
            "invoke": f"{base_url}/webhook/sync",
            "invoke_async": f"{base_url}/webhook",
            "health": f"{base_url}/health",
            "agent_card": f"{base_url}/.well-known/agent.json",
        },
        "status": "active" if heartbeat_connected(agent) else "inactive",
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if pricing:
        card["pricing"] = pricing

    card["signature"] = _sign_agent_card(agent, card)
    return card


def _pricing_from_agent(agent: ZyndAIAgent) -> dict[str, str] | None:
    price = agent.agent_config.price
    if not price:
        return None

    parts = price.strip().split()
    return {
        "per_call": parts[0],
        "currency": parts[1] if len(parts) > 1 else "USD",
    }


def _sign_agent_card(agent: ZyndAIAgent, card: dict[str, Any]) -> str:
    signable = {key: value for key, value in card.items() if key != "signature"}
    message = json.dumps(signable, sort_keys=True).encode("utf-8")
    return sign(agent.keypair.private_key, message).removeprefix("ed25519:")


def sdk_a2a_card(agent: ZyndAIAgent | None) -> dict[str, Any]:
    if agent is None:
        raise HTTPException(status_code=503, detail="agent runtime is not ready")

    card = agent._build_card()  # noqa: SLF001 - SDK owns the A2A runtime card shape.
    base_url = str(agent.agent_config.entity_url or "").rstrip("/")
    skills = [skill.id for skill in (agent.agent_config.skills or [])]
    card["capability_summary"] = {"skills": skills}
    card["tags"] = agent.agent_config.tags or []
    card["endpoints"] = {
        "webhook": f"{base_url}/webhook",
        "webhook_sync": f"{base_url}/webhook/sync",
        "health": f"{base_url}/health",
        "agent_card": f"{base_url}/.well-known/agent.json",
    }
    card["identity"] = {
        "agent_id": sdk_agent_id(agent),
        "public_key": agent.keypair.public_key_string,
        "verified_by": "ZyndAI SDK",
    }
    return card


def _sdk_search_function():
    return getattr(dns_registry, "search_agents", None) or dns_registry.search_entities


def _call_sdk_search(**kwargs):
    sdk_search = _sdk_search_function()
    supported = set(signature(sdk_search).parameters)
    filtered = {key: value for key, value in kwargs.items() if key in supported}
    return sdk_search(**filtered)


def _search_results(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    if isinstance(result, dict):
        values = result.get("results") or result.get("agents") or result.get("entities") or []
        return [item for item in values if isinstance(item, dict)]
    return []


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _iso_freshness_s(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _extract_endpoint(item: dict[str, Any]) -> str:
    card = item.get("card") or {}
    endpoints = card.get("endpoints") or item.get("endpoints") or {}
    for key in ("invoke", "webhook_sync", "webhook"):
        endpoint = endpoints.get(key)
        if endpoint:
            if key in {"invoke", "webhook_sync"}:
                return str(endpoint).removesuffix("/webhook/sync").rstrip("/")
            return str(endpoint).removesuffix("/webhook").rstrip("/")
    return str(item.get("agent_url") or item.get("entity_url") or "").rstrip("/")


def _extract_capabilities(item: dict[str, Any]) -> list[str]:
    card = item.get("card") or {}
    capability_summary = item.get("capability_summary") or {}
    skills = capability_summary.get("skills") or card.get("capabilities") or item.get("capabilities")
    return _as_string_list(skills)


def search_agents(
    *,
    registry_url: str,
    keyword: str | None = None,
    query: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    skills: list[str] | None = None,
    protocols: list[str] | None = None,
    models: list[str] | None = None,
    min_trust_score: float | None = None,
    status: str = "active",
    developer_handle: str | None = None,
    entity_type: str = "agent",
    max_results: int = 10,
    federated: bool = True,
    enrich: bool = True,
    timeout_ms: int | None = 5000,
) -> list[CandidateAgent]:
    effective_query = query or keyword or ""
    result = _call_sdk_search(
        registry_url=registry_url,
        query=effective_query,
        keyword=effective_query,
        category=category,
        tags=tags,
        skills=skills or ([effective_query] if effective_query else None),
        protocols=protocols,
        models=models,
        min_trust_score=min_trust_score,
        status=status,
        developer_handle=developer_handle,
        entity_type=entity_type,
        max_results=max_results,
        federated=federated,
        enrich=enrich,
        timeout_ms=timeout_ms,
    )

    candidates: list[CandidateAgent] = []
    for item in _search_results(result):
        item_status = str(item.get("status", "unknown"))
        if status != "any" and item_status not in {status, "online" if status == "active" else status}:
            continue

        agent_url = _extract_endpoint(item)
        if not agent_url:
            continue

        card = item.get("card") or None
        score = float(item.get("score", 0.0) or 0.0)
        trust_score = float(item.get("trust_score", item.get("trust", score)) or 0.0)
        last_heartbeat = item.get("last_heartbeat")

        candidates.append(
            CandidateAgent(
                agent_id=str(item.get("agent_id") or item.get("entity_id") or "unknown"),
                name=str(item.get("name", "unknown-agent")),
                agent_url=agent_url,
                search_score=score,
                trust_score=trust_score,
                status=item_status,
                last_heartbeat=last_heartbeat,
                freshness_s=_iso_freshness_s(last_heartbeat),
                latency_s=item.get("latency_s") or item.get("latency"),
                category=item.get("category") or (card or {}).get("category"),
                tags=_as_string_list(item.get("tags") or (card or {}).get("tags")),
                capabilities=_extract_capabilities(item),
                protocols=_as_string_list(item.get("protocols") or (card or {}).get("protocols")),
                models=_as_string_list(item.get("models") or (card or {}).get("supported_models")),
                developer_handle=item.get("developer_handle"),
                card=card,
            )
        )

    return candidates


@dataclass
class WebhookRuntimeState:
    started_at: float
    webhook_requests_total: int = 0
    webhook_failures_total: int = 0
    webhook_success_total: int = 0
    total_latency_s: float = 0.0
    last_request_at: str | None = None
    last_error: str | None = None

    @classmethod
    def create(cls) -> "WebhookRuntimeState":
        return cls(started_at=time.monotonic())

    def record_success(self, latency_s: float) -> None:
        self.webhook_success_total += 1
        self.total_latency_s += latency_s
        self.last_request_at = _utc_now_iso()
        self.last_error = None

    def record_failure(self, error: str) -> None:
        self.webhook_failures_total += 1
        self.last_request_at = _utc_now_iso()
        self.last_error = error

    @property
    def average_latency_s(self) -> float:
        if self.webhook_success_total == 0:
            return 0.0
        return self.total_latency_s / self.webhook_success_total

    @property
    def success_rate(self) -> float:
        completed = self.webhook_success_total + self.webhook_failures_total
        if completed == 0:
            return 1.0
        return self.webhook_success_total / completed


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def install_shutdown_handlers(component: str, stop_callback: Callable[[], None]) -> None:
    def _handler(sig, _frame):
        log.info("[Health] %s received signal %s; shutting down cleanly", component, sig)
        try:
            stop_callback()
        except Exception as e:  # noqa: BLE001
            log.error("[Error] %s shutdown failed: %s", component, e)
        os._exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except ValueError:
            pass


async def registry_last_heartbeat(agent: ZyndAIAgent | None) -> str | None:
    if agent is None:
        return None

    agent_id = sdk_agent_id(agent)
    if not agent_id:
        return None

    url = f"{str(agent.agent_config.registry_url).rstrip('/')}/v1/entities/{agent_id}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.0)) as client:
            response = await client.get(url)
        if response.status_code == 200:
            return response.json().get("last_heartbeat")
    except httpx.HTTPError:
        return None
    return None


async def sdk_health(agent: ZyndAIAgent | None, state: WebhookRuntimeState) -> dict[str, Any]:
    return {
        "status": "healthy" if agent else "starting",
        "agent_id": sdk_agent_id(agent),
        "identity_verified": bool(agent.keypair.public_key_string) if agent else False,
        "uptime_seconds": round(time.monotonic() - state.started_at, 3),
        "webhook_requests_total": state.webhook_requests_total,
        "webhook_failures_total": state.webhook_failures_total,
        "average_latency_s": round(state.average_latency_s, 3),
        "success_rate": round(state.success_rate, 4),
        "last_request_at": state.last_request_at,
        "last_error": state.last_error,
        "last_heartbeat": await registry_last_heartbeat(agent),
        "heartbeat_connected": heartbeat_connected(agent),
    }


def build_startup_task_processor(
    *,
    agent: ZyndAIAgent,
    capability: str,
    build_data: Callable[[str], list[dict]],
    base_notes: list[str],
) -> Callable[[AgentMessage], AgentTaskResponse]:
    def process_message(message: AgentMessage) -> AgentTaskResponse:
        metadata = message.metadata or {}
        instruction = str(metadata.get("instruction", ""))
        task_id = str(metadata.get("task_id", message.message_id))

        raw = agent.invoke(f"{message.content}\nInstruction: {instruction}" if instruction else message.content)
        data = json.loads(raw)

        return AgentTaskResponse(
            task_id=task_id,
            agent_id=sdk_agent_id(agent) or "unknown",
            agent_name=agent.agent_config.name,
            capability=capability,
            data=data,
            notes=base_notes,
        )

    def sdk_handler(handler_input, task):
        message = handler_input.message
        log.info("[Webhook] Received request from %s", message.sender_id)
        log.info("[Sync] Processing %s task", capability)
        started = time.perf_counter()
        response = process_message(message)
        elapsed = time.perf_counter() - started
        log.info("[Response] Completed in %.3fs", elapsed)
        return response.model_dump(mode="json")

    agent.set_custom_agent(lambda text: json.dumps(build_data(text), ensure_ascii=False))
    agent.on_message(sdk_handler)
    return process_message


async def sync_webhook_response(
    *,
    agent: ZyndAIAgent | None,
    payload: dict[str, Any],
    state: WebhookRuntimeState,
    process_message: Callable[[AgentMessage], AgentTaskResponse],
    extra_notes: list[str] | None = None,
) -> AgentTaskResponse:
    if agent is None:
        raise HTTPException(status_code=500, detail="agent runtime is not ready")

    state.webhook_requests_total += 1
    started = time.perf_counter()

    try:
        message = AgentMessage.from_dict(payload)
    except Exception as e:  # noqa: BLE001
        state.record_failure(str(e))
        log.error("[Error] Invalid AgentMessage payload: %s", e)
        raise HTTPException(status_code=400, detail=f"invalid AgentMessage payload: {e}") from e

    log.info("[Webhook] Received request from %s", message.sender_id)
    log.info("[Sync] Processing %s", (message.metadata or {}).get("requested_capability", "task"))

    try:
        response = await _maybe_to_thread(process_message, message)
        if extra_notes:
            response = response.model_copy(update={"notes": [*response.notes, *extra_notes]})
    except HTTPException as e:
        state.record_failure(str(e.detail))
        log.error("[Error] Webhook sync failed: %s", e.detail)
        raise
    except Exception as e:  # noqa: BLE001
        state.record_failure(str(e))
        log.error("[Error] Webhook sync failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    elapsed = time.perf_counter() - started
    state.record_success(elapsed)
    log.info("[Response] Completed in %.3fs", elapsed)
    log.info(
        "[Metrics] requests=%d avg_latency=%.3fs failures=%d success_rate=%.0f%%",
        state.webhook_requests_total,
        state.average_latency_s,
        state.webhook_failures_total,
        state.success_rate * 100,
    )
    return response


async def async_webhook_response(
    *,
    agent: ZyndAIAgent | None,
    payload: dict[str, Any],
    state: WebhookRuntimeState,
    process_message: Callable[[AgentMessage], AgentTaskResponse],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    if agent is None:
        raise HTTPException(status_code=500, detail="agent runtime is not ready")

    state.webhook_requests_total += 1
    try:
        message = AgentMessage.from_dict(payload)
    except Exception as e:  # noqa: BLE001
        state.record_failure(str(e))
        log.error("[Error] Invalid async AgentMessage payload: %s", e)
        raise HTTPException(status_code=400, detail=f"invalid AgentMessage payload: {e}") from e

    log.info("[Webhook] Accepted async request from %s", message.sender_id)
    background_tasks.add_task(_run_async_task_with_metrics, process_message, message, state)
    return {
        "status": "accepted",
        "message_id": message.message_id,
        "conversation_id": message.conversation_id,
        "accepted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


async def _maybe_to_thread(func, *args):
    import asyncio

    return await asyncio.to_thread(func, *args)


def _run_async_task_with_metrics(process_message, message: AgentMessage, state: WebhookRuntimeState) -> None:
    started = time.perf_counter()
    try:
        process_message(message)
    except Exception as e:  # noqa: BLE001
        state.record_failure(str(e))
        log.error("[Error] Async webhook task failed: %s", e)
        return

    elapsed = time.perf_counter() - started
    state.record_success(elapsed)
    log.info("[Response] Async task completed in %.3fs", elapsed)
