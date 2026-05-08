from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from shared.schemas import CandidateAgent


@dataclass
class AgentObservation:
    latency_s: float = 1.5
    success_rate: float = 0.9
    quality_score: float = 0.8
    reliability: float = 0.9


@dataclass
class ReputationStore:
    observed: Dict[str, AgentObservation] = field(default_factory=dict)

    def score(self, agent_id: str, discovery_score: float) -> float:
        obs = self.observed.get(agent_id, AgentObservation())
        latency_component = 1.0 / (1.0 + obs.latency_s)
        return (
            (discovery_score * 0.35)
            + (obs.success_rate * 0.30)
            + (obs.quality_score * 0.20)
            + (obs.reliability * 0.10)
            + (latency_component * 0.05)
        )

    def score_candidate(self, candidate: CandidateAgent) -> float:
        obs = self.observed.get(candidate.agent_id, AgentObservation())
        observed_latency = candidate.latency_s if candidate.latency_s is not None else obs.latency_s
        latency_component = 1.0 / (1.0 + max(0.0, observed_latency))

        freshness_component = 0.7
        if candidate.freshness_s is not None:
            freshness_component = max(0.0, min(1.0, 1.0 - (candidate.freshness_s / 300.0)))

        heartbeat_component = 1.0 if candidate.status in {"active", "online"} else 0.0
        trust_component = max(candidate.trust_score, candidate.search_score)

        return (
            (trust_component * 0.30)
            + (heartbeat_component * 0.20)
            + (obs.success_rate * 0.20)
            + (latency_component * 0.15)
            + (freshness_component * 0.10)
            + (obs.quality_score * 0.05)
        )

    def update_observation(self, agent_id: str, *, latency_s: float, success: bool) -> None:
        prev = self.observed.get(agent_id, AgentObservation())
        new_latency = (prev.latency_s * 0.8) + (latency_s * 0.2)
        new_success_rate = (prev.success_rate * 0.9) + ((1.0 if success else 0.0) * 0.1)
        new_reliability = (prev.reliability * 0.9) + ((1.0 if success else 0.0) * 0.1)
        self.observed[agent_id] = AgentObservation(
            latency_s=new_latency,
            success_rate=new_success_rate,
            quality_score=prev.quality_score,
            reliability=new_reliability,
        )
