from __future__ import annotations

import asyncio

from zyndai_agent import dns_registry
from zyndai_agent.agent import ZyndAIAgent

from orchestrator.reputation import ReputationStore
from shared.schemas import CandidateAgent
from shared.utils import get_logger


log = get_logger("Discovery")


async def discover_and_rank(*, orchestrator_agent: ZyndAIAgent, store: ReputationStore, capability: str) -> list[CandidateAgent]:
    log.info("[Discovery] Searching %s agents...", capability)
    log.info("[Discovery] Filtering active agents only")

    search_result = await asyncio.to_thread(
        lambda: dns_registry.search_entities(
            registry_url=orchestrator_agent.agent_config.registry_url,
            query=capability,
            skills=[capability],
            status="active",
            entity_type="agent",
            max_results=10,
            federated=False,
            enrich=False,
        )
    )
    raw_results = search_result.get("results", [])

    candidates: list[CandidateAgent] = []
    for item in raw_results:
        status = str(item.get("status", "unknown"))
        if status != "active":
            continue
        agent_url = str(item.get("agent_url") or item.get("entity_url") or "").rstrip("/")
        if not agent_url:
            continue
        candidates.append(
            CandidateAgent(
                agent_id=str(item.get("agent_id") or item.get("entity_id") or "unknown"),
                name=str(item.get("name", "unknown-agent")),
                agent_url=f"{agent_url}",
                search_score=float(item.get("score", 0.0) or 0.0),
                status=status,
                last_heartbeat=item.get("last_heartbeat"),
                tags=list(item.get("tags", []) or []),
            )
        )

    ranked = sorted(candidates, key=lambda c: store.score(c.agent_id, c.search_score), reverse=True)
    log.info("[Discovery] Found %d compatible agents", len(ranked))
    if ranked:
        log.info("[Ranking] Selecting highest reputation agent...")
    return ranked
