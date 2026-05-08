from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException

from shared.config import get_settings
from shared.schemas import AgentTaskRequest, AgentTaskResponse
from shared.utils import get_logger, setup_logging
from shared.zynd_sdk import ZyndAIAgent


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("funding-agent")

PORT = 8102


def _service_url() -> str:
    if settings.service_url:
        return str(settings.service_url)
    return f"http://localhost:{int(os.getenv('PORT', PORT))}"


def _premium_required() -> bool:
    return os.getenv("PREMIUM_REQUIRED", "false").lower() in {"1", "true", "yes"}


def _premium_cost() -> float:
    try:
        return float(os.getenv("PREMIUM_COST_USD", "0.10"))
    except ValueError:
        return 0.10


agent: ZyndAIAgent | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global agent
    base = _service_url()
    agent = ZyndAIAgent(
        settings=settings,
        name="funding-agent",
        description="Extracts investment signals and likely funding dynamics for the idea.",
        capabilities=["funding-analysis", "vc-research", "investment-signals"],
        tags=["funding", "vc", "signals"],
        webhook_sync_url=f"{base}/webhook/sync",
        health_url=f"{base}/health",
        premium_required=_premium_required(),
        premium_cost_usd=_premium_cost(),
        initial_reputation={"latency": 1.4, "success_rate": 0.92, "quality_score": 8.2, "cost_score": 0.4},
        key_path=os.getenv("AGENT_KEY_PATH", ".keys/funding-agent.key"),
    )
    await agent.start()
    yield


app = FastAPI(title="Funding Intelligence Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(req: AgentTaskRequest, x_payment_token: str | None = Header(default=None)) -> AgentTaskResponse:
    assert agent is not None
    if agent.card.premium_required and not x_payment_token:
        cost = agent.card.premium_cost_usd or 0.1
        log.warning("[Payment] Payment required (simulated). cost=$%.2f", cost)
        raise HTTPException(
            status_code=402,
            detail={"error": "payment_required", "cost_usd": cost, "pay_to": "X-Payment-Token"},
        )

    log.info("[Funding] Generating investment signals...")
    q = req.query.lower()
    signals = [
        {
            "signal": "Clear expansion path to adjacent verticals",
            "why_it_matters": "Investors prefer wedge + expansion strategies that scale.",
            "who_pays_attention": ["Seed VCs", "Operator angels"],
            "confidence": 0.74,
        },
        {
            "signal": "Regulated industry pain with measurable ROI",
            "why_it_matters": "Budget owners in regulated sectors pay for compliant automation.",
            "who_pays_attention": ["Strategic investors", "Growth equity (later)"],
            "confidence": 0.78 if any(k in q for k in ["health", "finance", "insurance"]) else 0.65,
        },
        {
            "signal": "Data advantage via integrations (not proprietary data hoarding)",
            "why_it_matters": "Distribution and workflow capture beat raw-model differentiation.",
            "who_pays_attention": ["SaaS investors", "Platform funds"],
            "confidence": 0.71,
        },
    ]

    notes = ["Heuristic funding signals; premium gate simulates monetized agent service."]
    if x_payment_token:
        notes.append("Payment token accepted.")

    return AgentTaskResponse(
        task_id=req.task_id,
        agent_id=agent.agent_id,
        agent_name=agent.card.name,
        capability="funding-analysis",
        data=signals,
        notes=notes,
    )

