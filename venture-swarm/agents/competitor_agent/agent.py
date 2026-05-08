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
log = get_logger("competitor-agent")

PORT = 8103


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
        name="competitor-agent",
        description="Assesses existing solutions and competitive saturation.",
        capabilities=["competitor-analysis", "saturation-analysis"],
        tags=["competition", "moat", "positioning"],
        webhook_sync_url=f"{base}/webhook/sync",
        health_url=f"{base}/health",
        initial_reputation={"latency": 1.0, "success_rate": 0.95, "quality_score": 8.1, "cost_score": 0.1},
        key_path=os.getenv("AGENT_KEY_PATH", ".keys/competitor-agent.key"),
    )
    await agent.start()
    yield


app = FastAPI(title="Competitor Analysis Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(req: AgentTaskRequest) -> AgentTaskResponse:
    assert agent is not None
    log.info("[Competitors] Evaluating saturation...")
    q = req.query.lower()
    saturation = "Medium"
    if any(k in q for k in ["copilot", "assistant", "ai agent", "workflow automation"]):
        saturation = "High"
    if any(k in q for k in ["industrial", "construction", "maritime", "rural"]):
        saturation = "Low"

    items = [
        {
            "competitor_type": "Horizontal AI tooling",
            "examples": ["Generic copilots", "LLM platforms", "Automation suites"],
            "differentiation_angle": "Own a narrow workflow with deep integrations and outcomes-based pricing.",
            "saturation": saturation,
        },
        {
            "competitor_type": "Incumbent workflow software",
            "examples": ["Legacy SaaS vendors", "ERP add-ons"],
            "differentiation_angle": "Win on time-to-value and model-backed decision support (not just UI).",
            "saturation": "Medium",
        },
    ]

    return AgentTaskResponse(
        task_id=req.task_id,
        agent_id=agent.agent_id,
        agent_name=agent.card.name,
        capability="competitor-analysis",
        data=items,
        notes=["Heuristic competitive landscape synthesis."],
    )

