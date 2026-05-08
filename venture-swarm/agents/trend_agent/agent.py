from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.config import get_settings
from shared.schemas import AgentTaskRequest, AgentTaskResponse
from shared.utils import get_logger, setup_logging
from shared.zynd_sdk import ZyndAIAgent


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("trend-agent")

PORT = 8101


def _service_url() -> str:
    if settings.service_url:
        return str(settings.service_url)
    return f"http://localhost:{int(os.getenv('PORT', PORT))}"


agent: ZyndAIAgent | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global agent
    base = _service_url()
    agent = ZyndAIAgent(
        settings=settings,
        name="trend-agent",
        description="Identifies relevant macro and micro trends for a startup idea.",
        capabilities=["trend-analysis", "startup-trends", "ai-market-research"],
        tags=["trends", "markets", "timing"],
        webhook_sync_url=f"{base}/webhook/sync",
        health_url=f"{base}/health",
        initial_reputation={"latency": 1.1, "success_rate": 0.96, "quality_score": 8.6, "cost_score": 0.1},
        key_path=os.getenv("AGENT_KEY_PATH", ".keys/trend-agent.key"),
    )
    await agent.start()
    yield


app = FastAPI(title="Trend Research Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(req: AgentTaskRequest) -> AgentTaskResponse:
    assert agent is not None
    log.info("[Trend] Analyzing query for trends...")
    q = req.query.lower()
    items = []
    for trend, evidence, horizon in [
        ("AI copilots for niche vertical workflows", "Strong pull for automating repetitive knowledge work", "6-18 months"),
        ("Regulatory-ready AI (auditable, explainable)", "Enterprises shifting from POCs to compliant deployments", "12-24 months"),
        ("Synthetic data + privacy-preserving analytics", "Rising constraints on data sharing increases demand for alternatives", "12-24 months"),
    ]:
        confidence = 0.72
        if any(k in q for k in ["health", "medical", "hipaa", "clinical"]):
            if "regulatory" in trend.lower():
                confidence = 0.86
        items.append(
            {"trend": trend, "evidence": evidence, "time_horizon": horizon, "confidence": confidence}
        )

    return AgentTaskResponse(
        task_id=req.task_id,
        agent_id=agent.agent_id,
        agent_name=agent.card.name,
        capability="trend-analysis",
        data=items,
        notes=["Heuristic trend synthesis (no external APIs required)."],
    )

