from __future__ import annotations

from shared.schemas import AgentCard
from shared.utils import get_logger
from shared.zynd_sdk import ZyndClient

from orchestrator.reputation import ReputationStore, score


log = get_logger("Discovery")


async def discover_and_rank(
    *,
    client: ZyndClient,
    store: ReputationStore,
    capability: str,
) -> list[AgentCard]:
    log.info("[Discovery] Searching %s agents...", capability)
    agents = await client.search_agents(keyword=capability)
    log.info("[Discovery] Found %d agents", len(agents))

    def _rank_key(card: AgentCard) -> float:
        return score(store.effective_reputation(card))

    ranked = sorted(agents, key=_rank_key, reverse=True)
    if ranked:
        best = ranked[0]
        log.info("[Ranking] Selecting highest reputation agent: %s", best.name)
    return ranked

