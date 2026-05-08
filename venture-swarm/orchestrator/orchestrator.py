from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

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
    search_agents,
    sdk_agent_id,
    start_sdk_runtime,
    stop_sdk_runtime,
)


log = get_logger("Orchestrator")


@dataclass
class OrchestratorMetrics:
    started_at: float
    tasks_dispatched: int = 0
    failovers_triggered: int = 0
    active_agents_last_run: int = 0
    orchestrations_total: int = 0
    total_orchestration_latency_s: float = 0.0
    last_error: str | None = None

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def average_orchestration_time_s(self) -> float:
        if self.orchestrations_total == 0:
            return 0.0
        return self.total_orchestration_latency_s / self.orchestrations_total


class VentureSwarmOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rep = ReputationStore()
        self._metrics = OrchestratorMetrics(started_at=time.monotonic())
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
        log.info("[Health] venture-swarm-orchestrator startup complete")

    def stop(self) -> None:
        log.info("[Heartbeat] venture-swarm-orchestrator shutting down")
        stop_sdk_runtime(self._agent)

    def health(self) -> dict:
        return {
            "status": "healthy",
            "agent_id": sdk_agent_id(self._agent),
            "heartbeat_connected": heartbeat_connected(self._agent),
            "uptime_seconds": round(self._metrics.uptime_seconds, 3),
            "tasks_dispatched": self._metrics.tasks_dispatched,
            "failovers_triggered": self._metrics.failovers_triggered,
            "active_agents": self._metrics.active_agents_last_run,
            "orchestrations_total": self._metrics.orchestrations_total,
            "average_orchestration_time_s": round(self._metrics.average_orchestration_time_s, 3),
            "last_error": self._metrics.last_error,
        }

    async def network(self) -> dict:
        registry_url = str(self._settings.zynd_registry_url or self._settings.directory_url).rstrip("/")
        try:
            candidates = await asyncio.to_thread(
                lambda: search_agents(
                    registry_url=registry_url,
                    query="",
                    status="active",
                    entity_type="agent",
                    max_results=50,
                    federated=True,
                    enrich=True,
                )
            )
        except Exception as e:  # noqa: BLE001
            self._metrics.last_error = str(e)
            log.warning("[Error] Network status discovery failed: %s", e)
            return {
                "status": "degraded",
                "registry_url": registry_url,
                "active_agents": 0,
                "error": str(e),
                "orchestrator": self.health(),
                "agents": [],
            }

        seen: set[str] = set()
        agents = []
        for candidate in sorted(candidates, key=lambda item: item.name):
            if candidate.agent_id in seen:
                continue
            seen.add(candidate.agent_id)
            agents.append(
                {
                    "name": candidate.name,
                    "agent_id": candidate.agent_id,
                    "status": candidate.status,
                    "category": candidate.category,
                    "capabilities": candidate.capabilities,
                    "tags": candidate.tags,
                    "protocols": candidate.protocols,
                    "trust_score": candidate.trust_score,
                    "latency_s": candidate.latency_s,
                    "freshness_s": candidate.freshness_s,
                    "last_heartbeat": candidate.last_heartbeat,
                    "endpoints": (candidate.card or {}).get("endpoints", {}),
                }
            )

        log.info("[Metrics] active_agents=%d network_status=ok", len(agents))
        return {
            "status": "ok",
            "registry_url": registry_url,
            "active_agents": len(agents),
            "orchestrator": self.health(),
            "agents": agents,
        }

    async def run(self, query: str) -> StartupReport:
        started = time.perf_counter()
        tasks = plan(query)
        conversation_id = str(uuid.uuid4())

        discovery_results = await asyncio.gather(
            *[
                discover_and_rank(orchestrator_agent=self._agent, store=self._rep, capability=t.capability)
                for t in tasks.tasks
            ]
        )

        by_capability = {tasks.tasks[i].capability: discovery_results[i] for i in range(len(tasks.tasks))}
        self._metrics.active_agents_last_run = len(
            {candidate.agent_id for candidates in discovery_results for candidate in candidates}
        )
        log.info("[Metrics] active_agents=%d", self._metrics.active_agents_last_run)

        payment_token = self._settings.premium_payment_token
        if payment_token:
            log.info("[Orchestrator] Premium payment token configured.")

        async def _run_task(t):
            candidates = by_capability.get(t.capability, [])
            try:
                return await dispatch_with_failover(
                    sender_agent=self._agent,
                    task=t,
                    query=tasks.query,
                    candidates=candidates,
                    store=self._rep,
                    payment_token=payment_token,
                    conversation_id=conversation_id,
                )
            except Exception as e:  # noqa: BLE001
                self._metrics.last_error = str(e)
                log.warning("[Failover] Primary pool failed for %s: %s", t.capability, e)
                fresh = await discover_and_rank(orchestrator_agent=self._agent, store=self._rep, capability=t.capability)
                tried = {c.agent_id for c in candidates}
                remaining = [c for c in fresh if c.agent_id not in tried] or fresh
                log.warning("[Recovery] Retrying %s task dispatch with %d candidate(s)", t.capability, len(remaining))
                return await dispatch_with_failover(
                    sender_agent=self._agent,
                    task=t,
                    query=tasks.query,
                    candidates=remaining,
                    store=self._rep,
                    payment_token=payment_token,
                    conversation_id=conversation_id,
                )

        dispatches = await asyncio.gather(*[_run_task(t) for t in tasks.tasks])
        self._metrics.tasks_dispatched += len(dispatches)
        self._metrics.failovers_triggered += sum(d.failovers for d in dispatches)

        trace = [
            {
                "task_id": d.response.task_id,
                "capability": d.response.capability,
                "agent": d.used_agent.name,
                "agent_id": d.used_agent.agent_id,
                "latency_s": round(d.latency_s, 3),
                "failovers": d.failovers,
                "conversation_id": conversation_id,
                "agent_status": d.used_agent.status,
                "last_heartbeat": d.used_agent.last_heartbeat,
            }
            for d in dispatches
        ]

        responses = {d.response.capability: d.response for d in dispatches}

        report = aggregate(
            query=query,
            trend=responses["trend-analysis"],
            funding=responses["funding-analysis"],
            competitors=responses["competitor-analysis"],
            market_gaps=responses["market-gap-analysis"],
            risks=responses["risk-analysis"],
            agent_trace=trace,
        )
        elapsed = time.perf_counter() - started
        self._metrics.orchestrations_total += 1
        self._metrics.total_orchestration_latency_s += elapsed
        self._metrics.last_error = None
        avg_latency = sum(d.latency_s for d in dispatches) / max(1, len(dispatches))
        success_rate = self._rep.success_rate()
        log.info(
            "[Metrics] active_agents=%d avg_latency=%.3fs failovers=%d success_rate=%.0f%% orchestration_time=%.3fs",
            self._metrics.active_agents_last_run,
            avg_latency,
            sum(d.failovers for d in dispatches),
            success_rate * 100,
            elapsed,
        )
        return report
