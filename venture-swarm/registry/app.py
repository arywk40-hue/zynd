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
    developer_id: str | None = None
    developer_handle: str | None = None
    developer_proof: dict[str, Any] | None = None
    entity_name: str | None = None
    version: str | None = None
    fqan: str | None = None


class RegisterAgentV1Response(BaseModel):
    entity_id: str
    agent_id: str
    fqan: str | None = None


class SearchV1Request(BaseModel):
    query: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    skills: list[str] | None = None
    protocols: list[str] | None = None
    models: list[str] | None = None
    min_trust_score: float | None = None
    status: str | None = None
    developer_handle: str | None = None
    fqan: str | None = None
    entity_type: str | None = None
    max_results: int = 10
    offset: int = 0
    federated: bool = False
    enrich: bool = False
    timeout_ms: int | None = None


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
    trust_score: float
    protocols: list[str]
    models: list[str]
    developer_id: str | None
    developer_handle: str | None
    entity_name: str | None
    version: str | None
    fqan: str | None
    last_heartbeat: str
    updated_mono: float


_agents: Dict[str, _Entry] = {}
_started_at = time.monotonic()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _entity_id_from_public_key(public_key: str, entity_type: str) -> str:
    key_b64 = public_key.removeprefix("ed25519:")
    try:
        public_key_bytes = base64.b64decode(key_b64)
        return generate_entity_id(public_key_bytes, entity_type)
    except Exception:  # noqa: BLE001
        return f"agdns:{abs(hash((public_key, entity_type))) % (10**16):016d}"


def _normalize_zns_part(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "unnamed"


def _build_fqan(developer_handle: str | None, entity_name: str | None) -> str | None:
    if not developer_handle or not entity_name:
        return None
    return (
        f"{settings.zns_root.rstrip('/')}/"
        f"{_normalize_zns_part(developer_handle)}/"
        f"{_normalize_zns_part(entity_name)}"
    )


def _fqan_matches(entry_fqan: str | None, requested_fqan: str) -> bool:
    if not entry_fqan:
        return False
    requested = requested_fqan.strip("/")
    entry = entry_fqan.strip("/")
    return entry == requested or entry.endswith(f"/{requested}")


def _latest_binding(entries: list[_Entry]) -> _Entry | None:
    if not entries:
        return None
    return sorted(
        entries,
        key=lambda entry: (
            entry.status == "active",
            entry.version or "",
            entry.updated_mono,
        ),
        reverse=True,
    )[0]


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
        "trust_score": entry.trust_score,
        "score_breakdown": {"base": entry.score, "trust": entry.trust_score},
        "status": entry.status,
        "protocols": entry.protocols,
        "models": entry.models,
        "developer_id": entry.developer_id,
        "developer_handle": entry.developer_handle,
        "entity_name": entry.entity_name,
        "version": entry.version,
        "fqan": entry.fqan,
        "last_heartbeat": entry.last_heartbeat,
    }
    if enrich:
        result["card"] = {
            "agent_id": entry.entity_id,
            "fqan": entry.fqan,
            "developer_handle": entry.developer_handle,
            "entity_name": entry.entity_name,
            "version": entry.version,
            "name": entry.name,
            "description": entry.summary,
            "category": entry.category,
            "tags": entry.tags,
            "capabilities": entry.capability_summary.get("skills", []),
            "protocols": entry.protocols,
            "supported_models": entry.models,
            "status": entry.status,
            "endpoints": {
                "invoke": f"{entry.entity_url.rstrip('/')}/webhook/sync",
                "invoke_async": f"{entry.entity_url.rstrip('/')}/webhook",
                "health": f"{entry.entity_url.rstrip('/')}/health",
                "agent_card": f"{entry.entity_url.rstrip('/')}/.well-known/agent.json",
            },
            "identity": {
                "agent_id": entry.entity_id,
                "fqan": entry.fqan,
                "developer_handle": entry.developer_handle,
                "entity_name": entry.entity_name,
                "public_key": entry.public_key,
                "verified_by": "ZyndAI registry",
            },
        }
    return result


app = FastAPI(title="VentureSwarm Directory", version="0.2.0")


@app.get("/health")
async def health() -> dict[str, int | float | str]:
    active_agents = sum(1 for entry in _agents.values() if entry.status == "active")
    log.info("[Metrics] active_agents=%d registered_agents=%d", active_agents, len(_agents))
    return {
        "status": "ok",
        "agents": len(_agents),
        "active_agents": active_agents,
        "uptime_seconds": round(time.monotonic() - _started_at, 3),
    }


@app.post("/v1/entities", response_model=RegisterAgentV1Response)
@app.post("/v1/agents", response_model=RegisterAgentV1Response)
async def register_v1(req: RegisterAgentV1Request) -> RegisterAgentV1Response:
    entity_url = (req.entity_url or req.agent_url or "").rstrip("/")
    entity_id = _entity_id_from_public_key(req.public_key, req.entity_type)
    skills = list((req.capability_summary or {}).get("skills") or [])
    if not skills:
        skills = list(req.tags)
    entity_name = _normalize_zns_part(req.entity_name or req.name)
    developer_handle = _normalize_zns_part(req.developer_handle) if req.developer_handle else None
    fqan = req.fqan or _build_fqan(developer_handle, entity_name)

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
        trust_score=0.85,
        protocols=["webhook", "webhook-sync", "agent-card"],
        models=[],
        developer_id=req.developer_id,
        developer_handle=developer_handle,
        entity_name=entity_name,
        version=req.version or "0.1.0",
        fqan=fqan,
        last_heartbeat=_utc_now_iso(),
        updated_mono=time.monotonic(),
    )
    log.info("[Directory] Registered %s (%s)", req.name, entity_id)
    if fqan:
        log.info("[ZNS] Registered: %s", fqan)
        log.info("[ZNS] Resolved: %s -> %s", fqan, entity_id)
    return RegisterAgentV1Response(entity_id=entity_id, agent_id=entity_id, fqan=fqan)


@app.put("/v1/entities/{entity_id}")
async def update_entity_v1(entity_id: str, updates: dict[str, Any]) -> dict[str, bool]:
    entry = _agents.get(entity_id)
    if not entry:
        raise HTTPException(status_code=404, detail="agent not found")

    for field_name in [
        "name",
        "category",
        "summary",
        "tags",
        "developer_id",
        "developer_handle",
        "entity_name",
        "version",
        "fqan",
    ]:
        if field_name in updates:
            if field_name in {"developer_handle", "entity_name"} and updates[field_name]:
                setattr(entry, field_name, _normalize_zns_part(str(updates[field_name])))
            else:
                setattr(entry, field_name, updates[field_name])
    if "entity_url" in updates:
        entry.entity_url = str(updates["entity_url"]).rstrip("/")
    if "capability_summary" in updates:
        entry.capability_summary = dict(updates["capability_summary"] or {})
    if not entry.fqan:
        entry.fqan = _build_fqan(entry.developer_handle, entry.entity_name)
    entry.updated_mono = time.monotonic()
    if entry.fqan:
        log.info("[ZNS] Rebound: %s -> %s", entry.fqan, entry.entity_id)
    return {"ok": True}


@app.post("/v1/search")
async def search_v1(req: SearchV1Request) -> dict[str, Any]:
    query = (req.query or "").strip().lower()
    normalized_query = query.replace("-", " ")
    requested_tags = set((req.tags or []))
    requested_skills = set((req.skills or []))
    requested_protocols = set((req.protocols or []))
    requested_models = set((req.models or []))

    results: list[dict[str, Any]] = []
    for entry in _agents.values():
        if req.entity_type and entry.entity_type != req.entity_type:
            continue

        if req.status and req.status != "any":
            requested_status = "active" if req.status == "online" else req.status
            if entry.status != requested_status:
                continue

        if req.min_trust_score is not None and entry.trust_score < req.min_trust_score:
            continue

        if req.category and entry.category != req.category:
            continue

        if req.developer_handle and entry.developer_handle != req.developer_handle:
            continue

        if req.fqan and not _fqan_matches(entry.fqan, req.fqan):
            continue

        if requested_tags and not requested_tags.intersection(set(entry.tags)):
            continue

        entry_skills = set(entry.capability_summary.get("skills", []) or [])
        if requested_skills and not requested_skills.intersection(entry_skills):
            continue

        if requested_protocols and not requested_protocols.intersection(set(entry.protocols)):
            continue

        if requested_models and not requested_models.intersection(set(entry.models)):
            continue

        haystack = " ".join([
            entry.name,
            entry.summary,
            entry.fqan or "",
            entry.entity_name or "",
            entry.developer_handle or "",
            " ".join(entry.tags),
            " ".join(list(entry_skills)),
        ]).lower()
        normalized_haystack = haystack.replace("-", " ")
        if query and query not in haystack and normalized_query not in normalized_haystack:
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


@app.get("/v1/resolve")
async def resolve_v1(
    fqan: str | None = None,
    developer_handle: str | None = None,
    entity_name: str | None = None,
) -> dict[str, Any]:
    matches = []
    for entry in _agents.values():
        if fqan and not _fqan_matches(entry.fqan, fqan):
            continue
        if developer_handle and entry.developer_handle != _normalize_zns_part(developer_handle):
            continue
        if entity_name and entry.entity_name != _normalize_zns_part(entity_name):
            continue
        matches.append(entry)

    selected = _latest_binding(matches)
    if not selected:
        raise HTTPException(status_code=404, detail="ZNS name not found")
    log.info("[ZNS] Resolved: %s -> %s", selected.fqan, selected.entity_id)
    return _entry_to_search_result(selected, enrich=True)


@app.get("/v1/resolve/{developer_handle}/{entity_name}")
async def resolve_handle_v1(developer_handle: str, entity_name: str) -> dict[str, Any]:
    return await resolve_v1(developer_handle=developer_handle, entity_name=entity_name)


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
    log.info("[Heartbeat] %s connected to registry", entry.fqan or entry.name)

    try:
        while True:
            await websocket.receive_text()
            entry.status = "active"
            entry.last_heartbeat = _utc_now_iso()
            entry.updated_mono = time.monotonic()
            log.info("[Heartbeat] %s active", entry.fqan or entry.name)
    except WebSocketDisconnect:
        entry.status = "inactive"
        entry.updated_mono = time.monotonic()
        log.warning("[Heartbeat] %s reconnecting...", entry.fqan or entry.name)
        log.warning("[CRASH] %s heartbeat disconnected", entry.fqan or entry.name)
        log.warning("[Recovery] %s removed from active registry pool", entry.fqan or entry.name)
