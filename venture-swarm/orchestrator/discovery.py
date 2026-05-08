from __future__ import annotations

import asyncio

from zyndai_agent.agent import ZyndAIAgent

from orchestrator.reputation import ReputationStore
from shared.schemas import CandidateAgent
from shared.utils import get_logger
from shared.zynd_runtime import search_agents


log = get_logger("Discovery")


async def discover_and_rank(*, orchestrator_agent: ZyndAIAgent, store: ReputationStore, capability: str) -> list[CandidateAgent]:
    log.info('[Discovery] search_agents(keyword="%s")', capability)
    log.info("[Discovery] Filtering active agents only")

    candidates = await asyncio.to_thread(
        lambda: search_agents(
            registry_url=orchestrator_agent.agent_config.registry_url,
            keyword=capability,
            skills=[capability],
            status="active",
            limit=10,
        )
    )

    ranked = sorted(candidates, key=lambda c: store.score(c.agent_id, c.search_score), reverse=True)
    log.info("[Discovery] Found %d active compatible agents", len(ranked))
    if ranked:
        log.info("[Ranking] Selecting highest reputation agent...")
    return ranked
