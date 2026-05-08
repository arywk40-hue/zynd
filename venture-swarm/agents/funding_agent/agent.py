from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from zyndai_agent import dns_registry
from zyndai_agent.agent import AgentConfig, ZyndAIAgent
from zyndai_agent.message import AgentMessage

from shared.config import get_settings
from shared.schemas import AgentTaskResponse
from shared.utils import get_logger, setup_logging


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("funding-agent")

PORT = 8102


def _service_url() -> str:
    if settings.service_url:
        return str(settings.service_url).rstrip("/")
    return f"http://localhost:{int(os.getenv('PORT', PORT))}"


def _premium_required() -> bool:
    return os.getenv("PREMIUM_REQUIRED", "false").lower() in {"1", "true", "yes"}


def _premium_cost() -> float:
    try:
        return float(os.getenv("PREMIUM_COST_USD", "0.10"))
    except ValueError:
        return 0.10


def _load_agent_config() -> dict:
    config_path = Path(__file__).with_name("agent.config.json")
    return json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}


def _build_data(_: str) -> list[dict]:
    return []


agent: ZyndAIAgent | None = None
_agent_config: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    global agent, _agent_config
    _agent_config = _load_agent_config()
    registry_url = str(settings.zynd_registry_url or settings.directory_url).rstrip("/")

    agent = ZyndAIAgent(
        AgentConfig(
            name=_agent_config.get("name", "funding-agent"),
            description=_agent_config.get("description", "Funding analysis agent"),
            category=_agent_config.get("category", "market-intelligence"),
            tags=_agent_config.get("tags", ["funding"]),
            summary=_agent_config.get("summary", "Funding intelligence"),
            capabilities=_agent_config.get("capabilities", {"skills": ["funding-analysis"]}),
            webhook_port=int(_agent_config.get("webhook_port", 9102)),
            registry_url=registry_url,
            keypair_path=os.environ.get("ZYND_AGENT_KEYPAIR_PATH") or None,
            price=(f"${_premium_cost():.2f}" if _premium_required() else None),
            config_dir=".agent-funding",
        )
    )

    agent.set_custom_agent(lambda text: json.dumps(_build_data(text), ensure_ascii=False))
    agent.add_message_handler(lambda message, _: log.info("[Funding] Message received from %s", message.sender_id))

    try:
        dns_registry.register_agent(
            registry_url=registry_url,
            keypair=agent.keypair,
            name=agent.agent_config.name,
            agent_url=_service_url(),
            category=agent.agent_config.category,
            tags=agent.agent_config.tags,
            summary=agent.agent_config.summary,
            capability_summary=agent.agent_config.capabilities,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[Registration] Failed: %s", e)

    yield


app = FastAPI(title="Funding Intelligence Agent", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(payload: dict, x_payment_token: str | None = Header(default=None)) -> AgentTaskResponse:
    assert agent is not None

    if _premium_required() and not x_payment_token:
        cost = _premium_cost()
        raise HTTPException(
            status_code=402,
            detail={"error": "payment_required", "cost_usd": cost, "pay_to": "X-Payment-Token"},
        )

    msg = AgentMessage.from_dict(payload)
    instruction = str((msg.metadata or {}).get("instruction", ""))
    task_id = str((msg.metadata or {}).get("task_id", msg.message_id))

    raw = agent.invoke(f"{msg.content}\nInstruction: {instruction}" if instruction else msg.content)
    data = json.loads(raw)

    notes = ["No funding data source configured."]
    if x_payment_token:
        notes.append("Payment token received.")

    response = AgentTaskResponse(
        task_id=task_id,
        agent_id=agent.agent_id,
        agent_name=agent.agent_config.name,
        capability="funding-analysis",
        data=data,
        notes=notes,
    )
    agent.set_response(msg.message_id, json.dumps(response.model_dump(mode="json"), ensure_ascii=False))
    return response
