from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from zyndai_agent.agent import ZyndAIAgent

from agents.startup_compare_agent.prompts import SYSTEM_PROMPT
from shared.config import get_settings
from shared.llm import build_llm_data_factory
from shared.schemas import AgentTaskResponse
from shared.utils import get_logger, setup_logging
from shared.zynd_runtime import (
    WebhookRuntimeState,
    async_webhook_response,
    build_sdk_agent,
    build_startup_task_processor,
    install_shutdown_handlers,
    sdk_agent_card,
    sdk_health,
    start_sdk_runtime,
    stop_sdk_runtime,
    sync_webhook_response,
)


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("startup-compare-agent")

PORT = 8106


def _service_url() -> str:
    if settings.service_url:
        return str(settings.service_url).rstrip("/")
    return f"http://localhost:{int(os.getenv('PORT', PORT))}"


def _load_agent_config() -> dict:
    config_path = Path(__file__).with_name("agent.config.json")
    return json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}


_build_data = build_llm_data_factory(
    settings=settings,
    capability="startup-comparison",
    system_prompt=SYSTEM_PROMPT,
)


agent: ZyndAIAgent | None = None
_agent_config: dict = {}
_runtime_state = WebhookRuntimeState.create()
_process_message = None


def _stop_runtime() -> None:
    if agent is not None:
        stop_sdk_runtime(agent)


install_shutdown_handlers("startup-compare-agent", _stop_runtime)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global agent, _agent_config, _process_message
    _agent_config = _load_agent_config()

    agent = build_sdk_agent(
        settings=settings,
        config=_agent_config,
        service_url=_service_url(),
        default_name="startup-compare-agent",
        default_description="Startup comparison agent",
        default_port=9106,
        config_dir=".agent-startup-compare",
    )

    _process_message = build_startup_task_processor(
        agent=agent,
        capability="startup-comparison",
        build_data=_build_data,
        base_notes=["Uses configured LLM provider to compare similar startup funding, profit, and loss patterns."],
    )
    start_sdk_runtime(agent)
    log.info("[Heartbeat] %s connected to registry", agent.agent_config.name)

    try:
        yield
    finally:
        log.info("[Heartbeat] %s shutting down", agent.agent_config.name)
        stop_sdk_runtime(agent)


app = FastAPI(title="Startup Comparison Agent", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return await sdk_health(agent, _runtime_state)


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return sdk_agent_card(agent)


@app.post("/webhook", status_code=202)
async def webhook(payload: dict, background_tasks: BackgroundTasks) -> dict:
    assert _process_message is not None
    return await async_webhook_response(
        agent=agent,
        payload=payload,
        state=_runtime_state,
        process_message=_process_message,
        background_tasks=background_tasks,
    )


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(payload: dict) -> AgentTaskResponse:
    assert _process_message is not None
    return await sync_webhook_response(
        agent=agent,
        payload=payload,
        state=_runtime_state,
        process_message=_process_message,
    )
