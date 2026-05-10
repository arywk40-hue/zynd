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
from shared.schemas import AgentTaskResponse, StartupReport
from shared.utils import get_logger
from shared.zynd_runtime import (
    build_zns_fqan,
    ensure_local_developer_keypair,
    ensure_sdk_keypair,
    heartbeat_connected,
    search_agents,
    sdk_agent_id,
    sdk_payment_status,
    sdk_zns_identity,
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
                version="0.1.0",
                category="orchestration",
                tags=["orchestrator", "venture-swarm"],
                server_port=settings.orchestrator_sdk_webhook_port,
                registry_url=registry_url,
                keypair_path=keypair_path,
                config_dir=".agent-orchestrator",
                fqan=build_zns_fqan(settings.zns_root, settings.zns_developer_handle, "orchestrator"),
            )
        )
        self._agent.set_custom_agent(lambda input_text: input_text)

    def start(self) -> None:
        start_sdk_runtime(self._agent)
        identity = sdk_zns_identity(self._agent)
        log.info("[ZNS] Orchestrator identity: %s", identity["fqan"])
        log.info("[Heartbeat] venture-swarm-orchestrator connected to registry")
        log.info("[Health] venture-swarm-orchestrator startup complete")

    def stop(self) -> None:
        log.info("[Heartbeat] venture-swarm-orchestrator shutting down")
        stop_sdk_runtime(self._agent)

    def health(self) -> dict:
        identity = sdk_zns_identity(self._agent)
        health = {
            "status": "healthy",
            "agent_id": sdk_agent_id(self._agent),
            "fqan": identity["fqan"],
            "developer_handle": identity["developer_handle"],
            "entity_name": identity["entity_name"],
            "version": identity["version"],
            "heartbeat_connected": heartbeat_connected(self._agent),
            "uptime_seconds": round(self._metrics.uptime_seconds, 3),
            "tasks_dispatched": self._metrics.tasks_dispatched,
            "failovers_triggered": self._metrics.failovers_triggered,
            "active_agents": self._metrics.active_agents_last_run,
            "orchestrations_total": self._metrics.orchestrations_total,
            "average_orchestration_time_s": round(self._metrics.average_orchestration_time_s, 3),
            "last_error": self._metrics.last_error,
        }
        health.update(sdk_payment_status(self._agent, settings=self._settings))
        return health

    async def network(self) -> dict:
        registry_url = str(self._settings.zynd_registry_url or self._settings.directory_url).rstrip("/")
        try:
            candidates = await asyncio.to_thread(
                lambda: search_agents(
                    registry_url=registry_url,
                    query="",
                    status="active",
                    developer_handle=self._settings.zns_developer_handle,
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
        for candidate in sorted(candidates, key=lambda item: item.display_identity):
            if candidate.agent_id in seen:
                continue
            seen.add(candidate.agent_id)
            agents.append(
                {
                    "name": candidate.name,
                    "agent_id": candidate.agent_id,
                    "fqan": candidate.fqan,
                    "entity_name": candidate.entity_name,
                    "version": candidate.version,
                    "developer_handle": candidate.developer_handle,
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
        if self._settings.x402_enabled:
            log.info("[x402] SDK-native Base Sepolia payment routing enabled.")

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
                if remaining:
                    log.warning("[Recovery] %s selected", remaining[0].display_identity)
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
                "agent_fqan": d.used_agent.fqan,
                "agent_version": d.used_agent.version,
                "latency_s": round(d.latency_s, 3),
                "failovers": d.failovers,
                "conversation_id": conversation_id,
                "agent_status": d.used_agent.status,
                "last_heartbeat": d.used_agent.last_heartbeat,
            }
            for d in dispatches
        ]

        responses = {d.response.capability: d.response for d in dispatches}
        required_capabilities = [
            "trend-analysis",
            "funding-analysis",
            "benchmarking-analysis",
            "competitor-analysis",
            "startup-comparison",
            "market-gap-analysis",
            "financial-signal-analysis",
            "risk-analysis",
        ]

        for capability in required_capabilities:
            if capability in responses:
                continue
            log.warning("[Recovery] Missing %s response; using empty fallback payload", capability)
            responses[capability] = AgentTaskResponse(
                task_id=f"missing-{capability}",
                agent_id="unavailable",
                agent_name="unavailable",
                capability=capability,
                data=[],
                notes=["No successful response returned for this capability; fallback data applied."],
            )

        report = aggregate(
            query=query,
            trend=responses["trend-analysis"],
            funding=responses["funding-analysis"],
            benchmarking=responses["benchmarking-analysis"],
            competitors=responses["competitor-analysis"],
            startup_comparisons=responses["startup-comparison"],
            market_gaps=responses["market-gap-analysis"],
            financial_signals=responses["financial-signal-analysis"],
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
