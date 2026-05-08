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
log = get_logger("market-gap-agent")

PORT = 8104


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
        name="market-gap-agent",
        description="Detects underserved segments and framing for a strong wedge.",
        capabilities=["market-gap-analysis", "underserved-market-detection"],
        tags=["gaps", "wedge", "segmentation"],
        webhook_sync_url=f"{base}/webhook/sync",
        health_url=f"{base}/health",
        initial_reputation={"latency": 0.9, "success_rate": 0.96, "quality_score": 8.4, "cost_score": 0.1},
        key_path=os.getenv("AGENT_KEY_PATH", ".keys/market-gap-agent.key"),
    )
    await agent.start()
    yield


app = FastAPI(title="Market Gap Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/sync", response_model=AgentTaskResponse)
async def webhook_sync(req: AgentTaskRequest) -> AgentTaskResponse:
    assert agent is not None
    log.info("[Gaps] Searching for underserved segments...")
    q = req.query.lower()

    gaps = [
        {
            "gap": "Workflow-specific AI that produces audit-ready artifacts",
            "target_user": "Ops and compliance leaders",
            "value_prop": "Automate documentation and decisions with traceability.",
            "why_now": "Enterprises demand proof and governance for AI output.",
            "confidence": 0.77,
        },
        {
            "gap": "Field-worker-first AI for low-connectivity environments",
            "target_user": "Distributed teams (construction, rural health, utilities)",
            "value_prop": "Offline-friendly assistive guidance + structured handoffs.",
            "why_now": "Mobile models and edge inference make it practical.",
            "confidence": 0.82 if any(k in q for k in ["rural", "field", "offline"]) else 0.68,
        },
    ]

    return AgentTaskResponse(
        task_id=req.task_id,
        agent_id=agent.agent_id,
        agent_name=agent.card.name,
        capability="market-gap-analysis",
        data=gaps,
        notes=["Heuristic market gap detection."],
    )

