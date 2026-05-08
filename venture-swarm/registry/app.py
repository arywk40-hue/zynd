from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.utils import get_logger, setup_logging


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("Directory")


class RegisterAgentV1Request(BaseModel):
    name: str
    agent_url: str
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    public_key: str
    signature: str
    capability_summary: dict[str, Any] | None = None


class RegisterAgentV1Response(BaseModel):
    agent_id: str


class SearchV1Request(BaseModel):
    query: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    skills: list[str] | None = None
    max_results: int = 10
    offset: int = 0
    federated: bool = False
    enrich: bool = False


@dataclass
class _Entry:
    agent_id: str
    name: str
    agent_url: str
    category: str
    tags: list[str]
    summary: str
    capability_summary: dict[str, Any]
    public_key: str
    signature: str
    status: str
    score: float
    last_heartbeat: str
    updated_mono: float


_agents: Dict[str, _Entry] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _entry_to_search_result(entry: _Entry, enrich: bool) -> dict[str, Any]:
    result = {
        "agent_id": entry.agent_id,
        "name": entry.name,
        "summary": entry.summary,
        "category": entry.category,
        "tags": entry.tags,
        "capability_summary": entry.capability_summary,
        "agent_url": entry.agent_url,
        "home_registry": str(settings.directory_url),
        "score": entry.score,
        "score_breakdown": {"base": entry.score},
        "status": entry.status,
        "last_heartbeat": entry.last_heartbeat,
    }
    if enrich:
        result["card"] = {
            "agent_id": entry.agent_id,
            "name": entry.name,
            "description": entry.summary,
            "tags": entry.tags,
            "capabilities": entry.capability_summary.get("skills", []),
            "endpoints": {
                "invoke": f"{entry.agent_url.rstrip('/')}/webhook/sync",
                "invoke_async": f"{entry.agent_url.rstrip('/')}/webhook",
                "health": f"{entry.agent_url.rstrip('/')}/health",
                "agent_card": f"{entry.agent_url.rstrip('/')}/.well-known/agent.json",
            },
        }
    return result


app = FastAPI(title="VentureSwarm Directory", version="0.2.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agents": str(len(_agents))}


@app.post("/v1/agents", response_model=RegisterAgentV1Response)
async def register_v1(req: RegisterAgentV1Request) -> RegisterAgentV1Response:
    # Deterministic lightweight ID strategy for local registry.
    agent_id = f"agdns:{abs(hash((req.public_key, req.agent_url, req.name))) % (10**16):016d}"
    _agents[agent_id] = _Entry(
        agent_id=agent_id,
        name=req.name,
        agent_url=req.agent_url.rstrip("/"),
        category=req.category,
        tags=req.tags,
        summary=req.summary,
        capability_summary=req.capability_summary or {},
        public_key=req.public_key,
        signature=req.signature,
        status="active",
        score=0.85,
        last_heartbeat=_utc_now_iso(),
        updated_mono=time.monotonic(),
    )
    log.info("[Directory] Registered %s (%s)", req.name, agent_id)
    return RegisterAgentV1Response(agent_id=agent_id)


@app.post("/v1/search")
async def search_v1(req: SearchV1Request) -> dict[str, Any]:
    query = (req.query or "").strip().lower()
    requested_tags = set((req.tags or []))
    requested_skills = set((req.skills or []))

    results: list[dict[str, Any]] = []
    for entry in _agents.values():
        if req.category and entry.category != req.category:
            continue

        if requested_tags and not requested_tags.intersection(set(entry.tags)):
            continue

        entry_skills = set(entry.capability_summary.get("skills", []) or [])
        if requested_skills and not requested_skills.intersection(entry_skills):
            continue

        haystack = " ".join([
            entry.name,
            entry.summary,
            " ".join(entry.tags),
            " ".join(list(entry_skills)),
        ]).lower()
        if query and query not in haystack:
            continue

        results.append(_entry_to_search_result(entry, req.enrich))

    results = results[req.offset : req.offset + req.max_results]
    return {
        "results": results,
        "total_found": len(results),
        "offset": req.offset,
        "has_more": False,
        "search_stats": {"federated": req.federated},
    }


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict[str, Any]:
    entry = _agents.get(agent_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")
    return _entry_to_search_result(entry, enrich=True)
