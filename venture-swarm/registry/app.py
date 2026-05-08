from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

from fastapi import FastAPI, HTTPException

from shared.config import get_settings
from shared.schemas import (
    AgentCard,
    HeartbeatRequest,
    HeartbeatResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    SearchAgentsResponse,
    utc_now,
)
from shared.utils import get_logger, setup_logging


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("Directory")


@dataclass
class _Entry:
    card: AgentCard
    ttl_s: float
    last_seen_mono: float


_agents: Dict[str, _Entry] = {}


def _is_alive(entry: _Entry) -> bool:
    return (time.monotonic() - entry.last_seen_mono) <= entry.ttl_s


def _cleanup() -> None:
    stale = [agent_id for agent_id, entry in _agents.items() if not _is_alive(entry)]
    for agent_id in stale:
        _agents.pop(agent_id, None)


app = FastAPI(title="VentureSwarm Directory", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    _cleanup()
    return {"status": "ok", "agents": str(len(_agents))}


@app.post("/register", response_model=RegisterAgentResponse)
async def register(req: RegisterAgentRequest) -> RegisterAgentResponse:
    _cleanup()
    card = req.card.model_copy(update={"last_seen": utc_now()})
    _agents[card.agent_id] = _Entry(card=card, ttl_s=req.ttl_s, last_seen_mono=time.monotonic())
    log.info("[Directory] Registered %s (%s) caps=%s", card.name, card.agent_id, ",".join(card.capabilities))
    return RegisterAgentResponse(ok=True)


@app.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(req: HeartbeatRequest) -> HeartbeatResponse:
    _cleanup()
    entry = _agents.get(req.agent_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")
    entry.last_seen_mono = time.monotonic()
    entry.card = entry.card.model_copy(update={"last_seen": utc_now()})
    return HeartbeatResponse(ok=True)


@app.get("/search", response_model=SearchAgentsResponse)
async def search(keyword: str) -> SearchAgentsResponse:
    _cleanup()
    kw = keyword.strip().lower()
    matches: list[AgentCard] = []
    for entry in _agents.values():
        card = entry.card
        haystack = " ".join(
            [
                card.name,
                card.description,
                " ".join(card.capabilities),
                " ".join(card.tags),
            ]
        ).lower()
        if kw in haystack:
            matches.append(card)
    return SearchAgentsResponse(keyword=keyword, agents=matches)


@app.get("/agents/{agent_id}", response_model=AgentCard)
async def get_agent(agent_id: str) -> AgentCard:
    _cleanup()
    entry = _agents.get(agent_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")
    return entry.card

