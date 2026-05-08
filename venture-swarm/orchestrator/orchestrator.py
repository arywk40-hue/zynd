from __future__ import annotations

import asyncio

from zyndai_agent.agent import AgentConfig, ZyndAIAgent

from orchestrator.aggregator import aggregate
from orchestrator.discovery import discover_and_rank
from orchestrator.dispatcher import dispatch_with_failover
from orchestrator.planner import plan
from orchestrator.reputation import ReputationStore
from shared.config import Settings
from shared.schemas import StartupReport
from shared.utils import get_logger
from shared.zynd_runtime import (
    ensure_local_developer_keypair,
    ensure_sdk_keypair,
    heartbeat_connected,
    sdk_agent_id,
    start_sdk_runtime,
    stop_sdk_runtime,
)


log = get_logger("Orchestrator")


class VentureSwarmOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rep = ReputationStore()
        ensure_local_developer_keypair()

        registry_url = str(settings.zynd_registry_url or settings.directory_url).rstrip("/")
        keypair_path = ensure_sdk_keypair(".keys/venture-swarm-orchestrator.json")
        self._agent = ZyndAIAgent(
            AgentConfig(
                name="venture-swarm-orchestrator",
                description="Orchestrator agent for decentralized startup intelligence.",
                category="orchestration",
                tags=["orchestrator", "venture-swarm"],
                server_port=settings.orchestrator_sdk_webhook_port,
                registry_url=registry_url,
                keypair_path=keypair_path,
                config_dir=".agent-orchestrator",
            )
        )
        self._agent.set_custom_agent(lambda input_text: input_text)

    def start(self) -> None:
        start_sdk_runtime(self._agent)
        log.info("[Heartbeat] venture-swarm-orchestrator connected to registry")

    def stop(self) -> None:
        log.info("[Heartbeat] venture-swarm-orchestrator shutting down")
        stop_sdk_runtime(self._agent)

    def health(self) -> dict:
        return {
            "status": "healthy",
            "agent_id": sdk_agent_id(self._agent),
            "heartbeat_connected": heartbeat_connected(self._agent),
        }

    async def run(self, query: str) -> StartupReport:
        tasks = plan(query)

        discovery_results = await asyncio.gather(
            *[
                discover_and_rank(orchestrator_agent=self._agent, store=self._rep, capability=t.capability)
                for t in tasks.tasks
            ]
        )

        by_capability = {tasks.tasks[i].capability: discovery_results[i] for i in range(len(tasks.tasks))}

        payment_token = self._settings.premium_payment_token
        if payment_token:
            log.info("[Orchestrator] Premium payment token configured.")

        async def _run_task(t):
            candidates = by_capability.get(t.capability, [])
            try:
                return await dispatch_with_failover(
                    sender_id=self._agent.agent_id,
                    task=t,
                    query=tasks.query,
                    candidates=candidates,
                    store=self._rep,
                    payment_token=payment_token,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[Failover] Primary pool failed for %s: %s", t.capability, e)
                fresh = await discover_and_rank(orchestrator_agent=self._agent, store=self._rep, capability=t.capability)
                tried = {c.agent_id for c in candidates}
                remaining = [c for c in fresh if c.agent_id not in tried] or fresh
                return await dispatch_with_failover(
                    sender_id=self._agent.agent_id,
                    task=t,
                    query=tasks.query,
                    candidates=remaining,
                    store=self._rep,
                    payment_token=payment_token,
                )

        dispatches = await asyncio.gather(*[_run_task(t) for t in tasks.tasks])

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
