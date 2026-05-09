from __future__ import annotations

import asyncio

from zyndai_agent.agent import ZyndAIAgent

from orchestrator.reputation import ReputationStore
from shared.schemas import CandidateAgent
from shared.utils import get_logger
from shared.zynd_runtime import parse_zns_fqan, search_agents


log = get_logger("Discovery")

_DISCOVERY_PROFILES = {
    "trend-analysis": {
        "query": "trend analysis",
        "tags": ["startup", "trends", "trend-analysis"],
        "skills": ["trend-analysis", "startup-trends"],
        "entity_name": "trend-agent",
    },
    "funding-analysis": {
        "query": "funding analysis",
        "tags": ["startup", "funding", "venture-capital", "funding-analysis"],
        "skills": ["funding-analysis", "vc-analysis", "investment-signals"],
        "entity_name": "funding-agent",
    },
    "benchmarking-analysis": {
        "query": "startup benchmarking",
        "tags": ["startup", "benchmarking", "comparables", "benchmarking-analysis"],
        "skills": ["benchmarking-analysis", "comparable-startups", "comp-set-analysis"],
        "entity_name": "benchmarking-agent",
    },
    "competitor-analysis": {
        "query": "competitor analysis",
        "tags": ["startup", "competition", "competitor-analysis"],
        "skills": ["competitor-analysis", "saturation-analysis"],
        "entity_name": "competitor-agent",
    },
    "startup-comparison": {
        "query": "startup comparison funding profit loss benchmark",
        "tags": ["startup", "comparison", "benchmarks", "funding-trajectory", "startup-comparison"],
        "skills": ["startup-comparison", "comparable-startups", "funding-trajectory-analysis"],
        "entity_name": "startup-compare-agent",
    },
    "market-gap-analysis": {
        "query": "market gap analysis",
        "tags": ["startup", "market", "market-gap-analysis"],
        "skills": ["market-gap-analysis", "underserved-market-detection"],
        "entity_name": "market-gap-agent",
    },
    "financial-signal-analysis": {
        "query": "financial signals",
        "tags": ["startup", "financial-signals", "unit-economics", "financial-signal-analysis"],
        "skills": ["financial-signal-analysis", "unit-economics", "burn-runway"],
        "entity_name": "financial-signals-agent",
    },
    "risk-analysis": {
        "query": "risk analysis",
        "tags": ["startup", "risk", "risk-analysis"],
        "skills": ["risk-analysis", "regulatory-risk-analysis", "technical-risk-analysis"],
        "entity_name": "risk-agent",
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
    developer_handle, _ = parse_zns_fqan(getattr(orchestrator_agent.agent_config, "fqan", None))
    developer_handle = developer_handle or "venture-swarm"
    root = str(getattr(orchestrator_agent.agent_config, "fqan", "zns01.zynd.ai")).split(f"/{developer_handle}/")[0]
    fqan_hint = f"{root}/{developer_handle}/{profile.get('entity_name', capability)}"

    log.info(
        "[Discovery] Searching %s agents query=%r category=startup-intelligence tags=%s federated=True enrich=True",
        capability,
        query,
        tags,
    )
    log.info("[Resolution] Resolving latest %s version", fqan_hint)
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
            developer_handle=developer_handle,
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
            "[Ranking] %s trust=%.2f status=%s latency=%s freshness=%s score=%.2f endpoint=%s",
            candidate.display_identity,
            candidate.trust_score,
            candidate.status,
            f"{candidate.latency_s:.2f}s" if candidate.latency_s is not None else "unknown",
            f"{candidate.freshness_s:.1f}s" if candidate.freshness_s is not None else "unknown",
            candidate.rank_score,
            str(candidate.agent_url),
        )
    if ranked:
        log.info("[ZNS] Resolved: %s -> %s", ranked[0].display_identity, ranked[0].agent_id)
        log.info("[Selection] %s selected", ranked[0].display_identity)
    return ranked
