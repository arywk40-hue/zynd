from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from zyndai_agent.ed25519_identity import generate_entity_id

from shared.config import get_settings
from shared.utils import get_logger, setup_logging


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("Directory")


class RegisterAgentV1Request(BaseModel):
    name: str
    agent_url: str | None = None
    entity_url: str | None = None
    entity_type: str = "agent"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    public_key: str
    signature: str
    capability_summary: dict[str, Any] | None = None


class RegisterAgentV1Response(BaseModel):
    entity_id: str
    agent_id: str


class SearchV1Request(BaseModel):
    query: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    skills: list[str] | None = None
    status: str | None = None
    entity_type: str | None = None
    max_results: int = 10
    offset: int = 0
    federated: bool = False
    enrich: bool = False


@dataclass
class _Entry:
    entity_id: str
    entity_type: str
    name: str
    entity_url: str
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


def _entity_id_from_public_key(public_key: str, entity_type: str) -> str:
    key_b64 = public_key.removeprefix("ed25519:")
    try:
        public_key_bytes = base64.b64decode(key_b64)
        return generate_entity_id(public_key_bytes, entity_type)
    except Exception:  # noqa: BLE001
        return f"agdns:{abs(hash((public_key, entity_type))) % (10**16):016d}"


def _entry_to_search_result(entry: _Entry, enrich: bool) -> dict[str, Any]:
    result = {
        "entity_id": entry.entity_id,
        "agent_id": entry.entity_id,
        "entity_type": entry.entity_type,
        "name": entry.name,
        "summary": entry.summary,
        "category": entry.category,
        "tags": entry.tags,
        "capability_summary": entry.capability_summary,
        "entity_url": entry.entity_url,
        "agent_url": entry.entity_url,
        "home_registry": str(settings.directory_url),
        "score": entry.score,
        "score_breakdown": {"base": entry.score},
        "status": entry.status,
        "last_heartbeat": entry.last_heartbeat,
    }
    if enrich:
        result["card"] = {
            "agent_id": entry.entity_id,
            "name": entry.name,
            "description": entry.summary,
            "tags": entry.tags,
            "capabilities": entry.capability_summary.get("skills", []),
            "endpoints": {
                "invoke": f"{entry.entity_url.rstrip('/')}/webhook/sync",
                "invoke_async": f"{entry.entity_url.rstrip('/')}/webhook",
                "health": f"{entry.entity_url.rstrip('/')}/health",
                "agent_card": f"{entry.entity_url.rstrip('/')}/.well-known/agent-card.json",
            },
        }
    return result


app = FastAPI(title="VentureSwarm Directory", version="0.2.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agents": str(len(_agents))}


@app.post("/v1/entities", response_model=RegisterAgentV1Response)
@app.post("/v1/agents", response_model=RegisterAgentV1Response)
async def register_v1(req: RegisterAgentV1Request) -> RegisterAgentV1Response:
    entity_url = (req.entity_url or req.agent_url or "").rstrip("/")
    entity_id = _entity_id_from_public_key(req.public_key, req.entity_type)
    skills = list((req.capability_summary or {}).get("skills") or [])
    if not skills:
        skills = list(req.tags)

    _agents[entity_id] = _Entry(
        entity_id=entity_id,
        entity_type=req.entity_type,
        name=req.name,
        entity_url=entity_url,
        category=req.category,
        tags=req.tags,
        summary=req.summary,
        capability_summary={"skills": skills},
        public_key=req.public_key,
        signature=req.signature,
        status="registered",
        score=0.85,
        last_heartbeat=_utc_now_iso(),
        updated_mono=time.monotonic(),
    )
    log.info("[Directory] Registered %s (%s)", req.name, entity_id)
    return RegisterAgentV1Response(entity_id=entity_id, agent_id=entity_id)


@app.put("/v1/entities/{entity_id}")
async def update_entity_v1(entity_id: str, updates: dict[str, Any]) -> dict[str, bool]:
    entry = _agents.get(entity_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")

    for field_name in ["name", "category", "summary", "tags"]:
        if field_name in updates:
            setattr(entry, field_name, updates[field_name])
    if "entity_url" in updates:
        entry.entity_url = str(updates["entity_url"]).rstrip("/")
    if "capability_summary" in updates:
        entry.capability_summary = dict(updates["capability_summary"] or {})
    entry.updated_mono = time.monotonic()
    return {"ok": True}


@app.post("/v1/search")
async def search_v1(req: SearchV1Request) -> dict[str, Any]:
    query = (req.query or "").strip().lower()
    requested_tags = set((req.tags or []))
    requested_skills = set((req.skills or []))

    results: list[dict[str, Any]] = []
    for entry in _agents.values():
        if req.entity_type and entry.entity_type != req.entity_type:
            continue

        if req.status and req.status != "any" and entry.status != req.status:
            continue

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


@app.get("/v1/entities/{entity_id}")
async def get_entity_v1(entity_id: str) -> dict[str, Any]:
    entry = _agents.get(entity_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")
    return _entry_to_search_result(entry, enrich=True)


@app.get("/v1/entities/{entity_id}/card")
async def get_entity_card_v1(entity_id: str) -> dict[str, Any]:
    entry = _agents.get(entity_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")
    return _entry_to_search_result(entry, enrich=True)["card"]


@app.websocket("/v1/entities/{entity_id}/ws")
async def heartbeat_ws(websocket: WebSocket, entity_id: str) -> None:
    entry = _agents.get(entity_id)
    if not entry:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    entry.status = "active"
    entry.last_heartbeat = _utc_now_iso()
    entry.updated_mono = time.monotonic()
    log.info("[Heartbeat] %s connected to registry", entry.name)

    try:
        while True:
            await websocket.receive_text()
            entry.status = "active"
            entry.last_heartbeat = _utc_now_iso()
            entry.updated_mono = time.monotonic()
            log.info("[Heartbeat] %s active", entry.name)
    except WebSocketDisconnect:
        entry.status = "inactive"
        entry.updated_mono = time.monotonic()
        log.warning("[Heartbeat] %s reconnecting...", entry.name)
