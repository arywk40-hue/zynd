from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from zyndai_agent.agent import ZyndAIAgent
from zyndai_agent.message import AgentMessage

from agents.benchmarking_agent.prompts import SYSTEM_PROMPT
from shared.config import get_settings
from shared.llm import build_llm_data_factory
from shared.schemas import AgentTaskResponse
from shared.utils import get_logger, setup_logging
from shared.zynd_runtime import (
    WebhookRuntimeState,
    async_webhook_response,
    build_sdk_agent,
    install_shutdown_handlers,
    sdk_agent_id,
    sdk_agent_card,
    sdk_health,
    search_agents,
    start_sdk_runtime,
    stop_sdk_runtime,
    sync_webhook_response,
)


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("benchmarking-agent")

PORT = 8106


def _service_url() -> str:
    if settings.service_url:
        return str(settings.service_url).rstrip("/")
    return f"http://localhost:{int(os.getenv('PORT', PORT))}"


def _premium_required() -> bool:
    return os.getenv("PREMIUM_REQUIRED", "false").lower() in {"1", "true", "yes"}


def _premium_cost() -> float:
    try:
        return float(os.getenv("PREMIUM_COST_USD", "0.15"))
    except ValueError:
        return 0.15


def _x402_enabled() -> bool:
    return bool(settings.x402_enabled)


def _x402_pay_to(_context) -> str:
    if agent is None or not getattr(agent, "pay_to_address", None):
        raise RuntimeError("benchmarking-agent SDK payment wallet is not ready")
    return str(agent.pay_to_address)


def _x402_price(_context) -> str:
    return f"${_premium_cost():.2f}"


def _load_agent_config() -> dict:
    config_path = Path(__file__).with_name("agent.config.json")
    return json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}


_build_data = build_llm_data_factory(
    settings=settings,
    capability="benchmarking-analysis",
    system_prompt=SYSTEM_PROMPT,
)


agent: ZyndAIAgent | None = None
_agent_config: dict = {}
_runtime_state = WebhookRuntimeState.create()
_process_message = None


def _stop_runtime() -> None:
    if agent is not None:
        stop_sdk_runtime(agent)


install_shutdown_handlers("benchmarking-agent", _stop_runtime)


def _summarize_financial_overlay(items: list[dict]) -> str:
    if not items:
        return ""
    signals = [str(item.get("signal", "")).strip() for item in items if item.get("signal")]
    signals = [signal for signal in signals if signal]
    if not signals:
        return ""
    return "; ".join(signals[:3])


def _request_financial_overlay(message: AgentMessage) -> tuple[list[dict], str | None]:
    if agent is None:
        return [], None

    log.info("[Swarm] benchmarking-agent requesting financial signals")
    candidates = search_agents(
        registry_url=agent.agent_config.registry_url,
        query="financial signals",
        category="startup-intelligence",
        tags=["startup", "financial-signals", "unit-economics"],
        skills=["financial-signal-analysis"],
        protocols=["webhook", "webhook-sync"],
        status="active",
        min_trust_score=0.0,
        developer_handle=settings.zns_developer_handle,
        max_results=5,
        federated=True,
        enrich=True,
    )
    if not candidates:
        log.warning("[Discovery] No financial-signal agents available")
        return [], None

    candidate = candidates[0]
    log.info("[Discovery] Found %s for financial signals", candidate.display_identity)
    log.info("[Coordination] routing request to %s", candidate.display_identity)

    collab_message = AgentMessage(
        content=message.content,
        sender_id=agent.entity_id,
        sender_public_key=agent.keypair.public_key_string,
        receiver_id=candidate.agent_id,
        message_type="query",
        conversation_id=message.conversation_id,
        in_reply_to=message.message_id,
        metadata={
            "task_id": f"collab-{message.message_id}",
            "instruction": "Provide financial signal proxies (revenue, burn, runway, margin) for comparable startups.",
            "requested_capability": "financial-signal-analysis",
        },
    )

    sync_url = f"{str(candidate.agent_url).rstrip('/')}/webhook/sync"
    try:
        response = agent.x402_processor.post(sync_url, json=collab_message.to_dict(), timeout=12)
    except Exception as e:  # noqa: BLE001
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code in {400, 401, 402, 403, 500} or "payment" in str(e).lower():
            log.info("[Coordination] Falling back to direct HTTP for financial signals")
            response = requests.post(sync_url, json=collab_message.to_dict(), timeout=12)
        else:
            log.warning("[Error] Financial collaboration failed: %s", e)
            return [], None

    if response.status_code != 200:
        log.warning("[Error] Financial collaboration returned HTTP %s", response.status_code)
        return [], None

    try:
        payload = AgentTaskResponse.model_validate(response.json())
    except Exception as e:  # noqa: BLE001
        log.warning("[Error] Financial collaboration response invalid: %s", e)
        return [], None

    log.info("[Response] %s returned financial signals", payload.agent_name)
    return payload.data, payload.agent_name


def _process(message: AgentMessage) -> AgentTaskResponse:
    assert agent is not None
    metadata = message.metadata or {}
    instruction = str(metadata.get("instruction", ""))
    task_id = str(metadata.get("task_id", message.message_id))

    raw = agent.invoke(f"{message.content}\nInstruction: {instruction}" if instruction else message.content)
    data = json.loads(raw)

    overlay_items, overlay_agent = _request_financial_overlay(message)
    overlay_summary = _summarize_financial_overlay(overlay_items)
    notes = [
        "Uses configured LLM provider for live benchmarking reasoning when available.",
        "Merged financial overlays from collaborative agent requests.",
    ]
    if overlay_summary:
        for item in data:
            if isinstance(item, dict):
                item["financial_overlay"] = overlay_summary
        log.info("[Merge] Added financial overlays to benchmarking set")
    if overlay_agent:
        notes.append(f"Collaborated with {overlay_agent} for financial signals.")

    return AgentTaskResponse(
        task_id=task_id,
        agent_id=sdk_agent_id(agent) or "unknown",
        agent_name=agent.agent_config.name,
        capability="benchmarking-analysis",
        data=data,
        notes=notes,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    global agent, _agent_config, _process_message
    _agent_config = _load_agent_config()

    agent = build_sdk_agent(
        settings=settings,
        config=_agent_config,
        service_url=_service_url(),
        default_name="benchmarking-agent",
        default_description="Benchmarking agent for comparable startups",
        default_port=9108,
        config_dir=".agent-benchmarking",
        price=(f"${_premium_cost():.2f}" if _premium_required() else None),
    )

    agent.set_custom_agent(lambda text: json.dumps(_build_data(text), ensure_ascii=False))

    def _sdk_handler(handler_input, _task):
        message = handler_input.message
        log.info("[Webhook] Received request from %s", message.sender_id)
        log.info("[Sync] Processing benchmarking-analysis task")
        started = time.perf_counter()
        response = _process(message)
        elapsed = time.perf_counter() - started
        log.info("[Response] Completed in %.3fs", elapsed)
        return response.model_dump(mode="json")

    agent.on_message(_sdk_handler)
    _process_message = _process

    start_sdk_runtime(agent)
    log.info("[Heartbeat] %s connected to registry", agent.agent_config.name)

    try:
        yield
    finally:
        log.info("[Heartbeat] %s shutting down", agent.agent_config.name)
        stop_sdk_runtime(agent)


app = FastAPI(title="Benchmarking Agent", version="0.2.0", lifespan=lifespan)


def _install_x402_middleware() -> None:
    if not _x402_enabled():
        return

    try:
        from x402 import x402ResourceServer
        from x402.http.facilitator_client import FacilitatorConfig, HTTPFacilitatorClient
        from x402.http.middleware.fastapi import PaywallConfig, payment_middleware
        from x402.http.types import PaymentOption, RouteConfig
        from x402.mechanisms.evm.exact import register_exact_evm_server
    except Exception as e:  # noqa: BLE001
        log.error("[x402] Payment middleware unavailable: %s", e)
        return

    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=settings.x402_facilitator_url))
    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server, networks=settings.x402_network)

    route_config = RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            pay_to=_x402_pay_to,
            price=_x402_price,
            network=settings.x402_network,
            max_timeout_seconds=300,
        ),
        description="Premium VentureSwarm benchmarking intelligence",
        mime_type="application/json",
    )
    middleware = payment_middleware(
        {
            "POST /webhook": route_config,
            "POST /webhook/sync": route_config,
        },
        server,
        paywall_config=PaywallConfig(app_name="VentureSwarm Benchmarking Agent", testnet=True),
        sync_facilitator_on_start=settings.x402_sync_facilitator_on_start,
    )

    @app.middleware("http")
    async def x402_middleware(request: Request, call_next):
        protected = request.url.path in {"/webhook", "/webhook/sync"}
        if not protected or not _premium_required():
            return await call_next(request)

        log.warning("[x402] premium-benchmarking-agent requires payment")
        log.info("[x402] Processing %s USDC payment...", settings.x402_network_name)
        response = await middleware(request, call_next)
        if response.status_code == 402:
            log.warning("[x402] Payment required or settlement failed")
        elif getattr(request.state, "payment_payload", None) is not None:
            log.info("[x402] Payment successful")
            log.info("[Dispatch] premium-benchmarking-agent executing analysis")
        return response

    log.info("[x402] Base Sepolia payment middleware enabled for premium-benchmarking-agent")


_install_x402_middleware()


@app.get("/health")
async def health() -> dict:
    return await sdk_health(agent, _runtime_state)


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return sdk_agent_card(agent)


@app.post("/webhook", status_code=202)
async def webhook(
    payload: dict,
    background_tasks: BackgroundTasks,
    request: Request,
    x_payment_token: str | None = Header(default=None),
) -> dict:
    assert _process_message is not None
    if _premium_required() and not _x402_enabled() and not x_payment_token:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "cost_usd": _premium_cost(),
                "pay_to": "X-Payment-Token",
                "x402_enabled": False,
            },
        )
    return await async_webhook_response(
        agent=agent,
        payload=payload,
        state=_runtime_state,
        process_message=_process_message,
        background_tasks=background_tasks,
    )


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(
    payload: dict,
    request: Request,
    x_payment_token: str | None = Header(default=None),
) -> AgentTaskResponse:
    assert agent is not None

    if _premium_required() and not _x402_enabled() and not x_payment_token:
        cost = _premium_cost()
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "cost_usd": cost,
                "pay_to": "X-Payment-Token",
                "x402_enabled": False,
            },
        )

    assert _process_message is not None
    payment_notes = []
    if getattr(request.state, "payment_payload", None) is not None:
        payment_notes.append("x402 payment verified on Base Sepolia.")
    if x_payment_token:
        payment_notes.append("Payment token received.")
    return await sync_webhook_response(
        agent=agent,
        payload=payload,
        state=_runtime_state,
        process_message=_process_message,
        extra_notes=payment_notes or None,
    )
