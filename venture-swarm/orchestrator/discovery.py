from __future__ import annotations

import asyncio

from zyndai_agent.agent import ZyndAIAgent

from orchestrator.reputation import ReputationStore
from shared.schemas import CandidateAgent
from shared.utils import get_logger
from shared.zynd_runtime import search_agents


log = get_logger("Discovery")

_DISCOVERY_PROFILES = {
    "trend-analysis": {
        "query": "trend analysis",
        "tags": ["startup", "trends", "trend-analysis"],
        "skills": ["trend-analysis", "startup-trends"],
    },
    "funding-analysis": {
        "query": "funding analysis",
        "tags": ["startup", "funding", "venture-capital", "funding-analysis"],
        "skills": ["funding-analysis", "vc-analysis", "investment-signals"],
    },
    "competitor-analysis": {
        "query": "competitor analysis",
        "tags": ["startup", "competition", "competitor-analysis"],
        "skills": ["competitor-analysis", "saturation-analysis"],
    },
    "market-gap-analysis": {
        "query": "market gap analysis",
        "tags": ["startup", "market", "market-gap-analysis"],
        "skills": ["market-gap-analysis", "underserved-market-detection"],
    },
    "risk-analysis": {
        "query": "risk analysis",
        "tags": ["startup", "risk", "risk-analysis"],
        "skills": ["risk-analysis", "regulatory-risk-analysis", "technical-risk-analysis"],
    },
}


async def discover_and_rank(*, orchestrator_agent: ZyndAIAgent, store: ReputationStore, capability: str) -> list[CandidateAgent]:
    profile = _DISCOVERY_PROFILES.get(
        capability,
        {"query": capability.replace("-", " "), "tags": [capability], "skills": [capability]},
    )
    tags = list(profile["tags"])
    skills = list(profile["skills"])
    query = str(profile["query"])

    log.info(
        "[Discovery] Searching %s agents query=%r category=startup-intelligence tags=%s federated=True enrich=True",
        capability,
        query,
        tags,
    )
    log.info("[Discovery] Filtering active agents only")

    candidates = await asyncio.to_thread(
        lambda: search_agents(
            registry_url=orchestrator_agent.agent_config.registry_url,
            query=query,
            category="startup-intelligence",
            tags=tags,
            skills=skills,
            protocols=["webhook", "webhook-sync"],
            min_trust_score=0.0,
            status="active",
            max_results=10,
            federated=True,
            enrich=True,
        )
    )

    active = [c for c in candidates if c.status in {"active", "online"}]
    ranked = sorted(active, key=store.score_candidate, reverse=True)
    ranked = [c.model_copy(update={"rank_score": store.score_candidate(c)}) for c in ranked]

    log.info("[Discovery] Found %d active compatible agents", len(ranked))
    for candidate in ranked:
        log.info(
            "[Ranking] %s trust=%.2f latency=%s freshness=%s score=%.2f",
            candidate.name,
            candidate.trust_score,
            f"{candidate.latency_s:.2f}s" if candidate.latency_s is not None else "unknown",
            f"{candidate.freshness_s:.1f}s" if candidate.freshness_s is not None else "unknown",
            candidate.rank_score,
        )
    if ranked:
        log.info("[Selection] %s selected", ranked[0].name)
    return ranked
