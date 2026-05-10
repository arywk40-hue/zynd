from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from zyndai_agent.agent import ZyndAIAgent

from agents.funding_agent.prompts import SYSTEM_PROMPT
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


def _x402_enabled() -> bool:
    return bool(settings.x402_enabled)


def _x402_pay_to(_context) -> str:
    if agent is None or not getattr(agent, "pay_to_address", None):
        raise RuntimeError("funding-agent SDK payment wallet is not ready")
    return str(agent.pay_to_address)


def _x402_price(_context) -> str:
    return f"${_premium_cost():.2f}"


def _load_agent_config() -> dict:
    config_path = Path(__file__).with_name("agent.config.json")
    return json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}


_build_data = build_llm_data_factory(
    settings=settings,
    capability="funding-analysis",
    system_prompt=SYSTEM_PROMPT,
)


agent: ZyndAIAgent | None = None
_agent_config: dict = {}
_runtime_state = WebhookRuntimeState.create()
_process_message = None


def _stop_runtime() -> None:
    if agent is not None:
        stop_sdk_runtime(agent)


install_shutdown_handlers("funding-agent", _stop_runtime)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global agent, _agent_config, _process_message
    _agent_config = _load_agent_config()

    agent = build_sdk_agent(
        settings=settings,
        config=_agent_config,
        service_url=_service_url(),
        default_name="funding-agent",
        default_description="Funding analysis agent",
        default_port=9102,
        config_dir=".agent-funding",
        price=(f"${_premium_cost():.2f}" if _premium_required() else None),
    )

    _process_message = build_startup_task_processor(
        agent=agent,
        capability="funding-analysis",
        build_data=_build_data,
        base_notes=["Uses configured LLM provider for live funding reasoning when available."],
    )
    start_sdk_runtime(agent)
    log.info("[Heartbeat] %s connected to registry", agent.agent_config.name)

    try:
        yield
    finally:
        log.info("[Heartbeat] %s shutting down", agent.agent_config.name)
        stop_sdk_runtime(agent)


app = FastAPI(title="Funding Intelligence Agent", version="0.2.0", lifespan=lifespan)


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
        description="Premium VentureSwarm funding intelligence",
        mime_type="application/json",
    )
    middleware = payment_middleware(
        {
            "POST /webhook": route_config,
            "POST /webhook/sync": route_config,
        },
        server,
        paywall_config=PaywallConfig(app_name="VentureSwarm Funding Agent", testnet=True),
        sync_facilitator_on_start=settings.x402_sync_facilitator_on_start,
    )

    @app.middleware("http")
    async def x402_middleware(request: Request, call_next):
        protected = request.url.path in {"/webhook", "/webhook/sync"}
        if not protected or not _premium_required():
            return await call_next(request)

        log.warning("[x402] premium-funding-agent requires payment")
        log.info("[x402] Processing %s USDC payment...", settings.x402_network_name)
        response = await middleware(request, call_next)
        if response.status_code == 402:
            log.warning("[x402] Payment required or settlement failed")
        elif getattr(request.state, "payment_payload", None) is not None:
            log.info("[x402] Payment successful")
            log.info("[Dispatch] premium-funding-agent executing analysis")
        return response

    log.info("[x402] Base Sepolia payment middleware enabled for premium-funding-agent")


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
