from __future__ import annotations

import asyncio

from zyndai_agent.agent import ZyndAIAgent

from orchestrator.reputation import ReputationStore
from shared.schemas import CandidateAgent
from shared.utils import get_logger


log = get_logger("Discovery")


async def discover_and_rank(*, orchestrator_agent: ZyndAIAgent, store: ReputationStore, capability: str) -> list[CandidateAgent]:
    log.info("[Discovery] Searching %s agents...", capability)

    raw_results = await asyncio.to_thread(
        lambda: orchestrator_agent.search_agents(
            keyword=capability,
            skills=[capability],
            limit=10,
            federated=False,
            enrich=False,
        )
    )

    candidates: list[CandidateAgent] = []
    for item in raw_results:
        agent_url = str(item.get("agent_url", "")).rstrip("/")
        if not agent_url:
            continue
        candidates.append(
            CandidateAgent(
                agent_id=str(item.get("agent_id", "unknown")),
                name=str(item.get("name", "unknown-agent")),
                agent_url=f"{agent_url}",
                search_score=float(item.get("score", 0.0) or 0.0),
                tags=list(item.get("tags", []) or []),
            )
        )

    ranked = sorted(candidates, key=lambda c: store.score(c.agent_id, c.search_score), reverse=True)
    log.info("[Discovery] Found %d compatible agents", len(ranked))
    if ranked:
        log.info("[Ranking] Selecting highest reputation agent...")
    return ranked
