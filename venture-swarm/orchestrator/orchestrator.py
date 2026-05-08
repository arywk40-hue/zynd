from __future__ import annotations

import asyncio

from orchestrator.aggregator import aggregate
from orchestrator.discovery import discover_and_rank
from orchestrator.dispatcher import dispatch_with_failover
from orchestrator.planner import plan
from orchestrator.reputation import ReputationStore
from shared.config import Settings
from shared.schemas import StartupReport
from shared.utils import get_logger
from shared.zynd_sdk import ZyndClient


log = get_logger("Orchestrator")


class VentureSwarmOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = ZyndClient(settings=settings)
        self._rep = ReputationStore()

    async def run(self, query: str) -> StartupReport:
        tasks = plan(query)

        # Discovery for each capability (parallel)
        discovery_results = await asyncio.gather(
            *[
                discover_and_rank(client=self._client, store=self._rep, capability=t.capability)
                for t in tasks.tasks
            ]
        )

        by_capability = {tasks.tasks[i].capability: discovery_results[i] for i in range(len(tasks.tasks))}

        payment_token = self._settings.premium_payment_token
        if payment_token:
            log.info("[Orchestrator] Premium payment token configured.")

        # Dispatch all tasks in parallel; each dispatch handles its own failover.
        dispatches = await asyncio.gather(
            *[
                dispatch_with_failover(
                    task=t,
                    query=tasks.query,
                    candidates=by_capability.get(t.capability, []),
                    store=self._rep,
                    payment_token=payment_token,
                )
                for t in tasks.tasks
            ]
        )

        trace = [
            {
                "task_id": d.response.task_id,
                "capability": d.response.capability,
                "agent": d.used_agent.name,
                "agent_id": d.used_agent.agent_id,
                "latency_s": round(d.latency_s, 3),
                "failovers": d.failovers,
            }
            for d in dispatches
        ]

        # Map responses for aggregation
        responses = {d.response.capability: d.response for d in dispatches}

        return aggregate(
            query=query,
            trend=responses["trend-analysis"],
            funding=responses["funding-analysis"],
            competitors=responses["competitor-analysis"],
            market_gaps=responses["market-gap-analysis"],
            risks=responses["regulatory-risk-analysis"],
            agent_trace=trace,
        )

