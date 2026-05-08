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
log = get_logger("risk-agent")

PORT = 8105


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
        name="risk-agent",
        description="Assesses regulatory and technical feasibility risks.",
        capabilities=["regulatory-risk-analysis", "technical-feasibility-analysis"],
        tags=["risk", "regulatory", "feasibility"],
        webhook_sync_url=f"{base}/webhook/sync",
        health_url=f"{base}/health",
        initial_reputation={"latency": 1.2, "success_rate": 0.95, "quality_score": 8.3, "cost_score": 0.1},
        key_path=os.getenv("AGENT_KEY_PATH", ".keys/risk-agent.key"),
    )
    await agent.start()
    yield


app = FastAPI(title="Risk Analysis Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(req: AgentTaskRequest) -> AgentTaskResponse:
    assert agent is not None
    log.info("[Risk] Assessing risks...")
    q = req.query.lower()
    severity = "Medium"
    if any(k in q for k in ["health", "medical", "finance", "insurance", "education"]):
        severity = "High"

    items = [
        {
            "risk": "Model hallucinations causing incorrect decisions",
            "category": "technical-feasibility-analysis",
            "severity": "High",
            "mitigation": "Use retrieval over trusted sources, constrain outputs, add human-in-the-loop for high-stakes steps.",
        },
        {
            "risk": "Data privacy and retention obligations",
            "category": "regulatory-risk-analysis",
            "severity": severity,
            "mitigation": "Minimize data, encrypt, use audit logs, adopt DPAs, support on-prem / VPC if needed.",
        },
        {
            "risk": "Integration complexity and change management",
            "category": "technical-feasibility-analysis",
            "severity": "Medium",
            "mitigation": "Start with 1-2 core integrations and measurable, narrow workflow outcomes.",
        },
    ]

    return AgentTaskResponse(
        task_id=req.task_id,
        agent_id=agent.agent_id,
        agent_name=agent.card.name,
        capability="regulatory-risk-analysis",
        data=items,
        notes=["Heuristic risk analysis; expand with domain specifics via prompt/LLM if configured."],
    )

