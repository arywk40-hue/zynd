from __future__ import annotations

import json
import os
import sys

from fastapi import FastAPI

from orchestrator.orchestrator import VentureSwarmOrchestrator
from shared.config import get_settings
from shared.schemas import StartupQuery, StartupReport
from shared.utils import get_logger, setup_logging


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("main")

orchestrator = VentureSwarmOrchestrator(settings)

app = FastAPI(title="VentureSwarm Orchestrator", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/report", response_model=StartupReport)
async def report(req: StartupQuery) -> StartupReport:
    log.info("[Orchestrator] Received query: %s", req.query)
    return await orchestrator.run(req.query)


def _cli() -> int:
    if len(sys.argv) < 2:
        print("Usage: python main.py \"your startup research query\"")
        return 2
    query = " ".join(sys.argv[1:])
    # Minimal CLI runner: requires directory + agents running separately.
    import asyncio

    rep = asyncio.run(orchestrator.run(query))
    print(json.dumps(rep.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(_cli())

