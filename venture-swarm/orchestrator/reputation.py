from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from shared.schemas import AgentCard, AgentReputation


def score(rep: AgentReputation) -> float:
    # Higher is better; clamp inputs already validated by Pydantic.
    latency_component = 1.0 / (1.0 + rep.latency)
    return (
        (rep.success_rate * 0.45)
        + ((rep.quality_score / 10.0) * 0.35)
        + (latency_component * 0.15)
        + ((1.0 - rep.cost_score) * 0.05)
    )


@dataclass
class ReputationStore:
    observed: Dict[str, AgentReputation] = field(default_factory=dict)

    def effective_reputation(self, card: AgentCard) -> AgentReputation:
        return self.observed.get(card.agent_id, card.reputation)

    def update_observation(self, card: AgentCard, *, latency_s: float, success: bool) -> None:
        prev = self.observed.get(card.agent_id, card.reputation)
        # Simple exponential-ish smoothing.
        new_latency = (prev.latency * 0.8) + (latency_s * 0.2)
        new_success_rate = (prev.success_rate * 0.9) + ((1.0 if success else 0.0) * 0.1)
        self.observed[card.agent_id] = AgentReputation(
            latency=new_latency,
            success_rate=new_success_rate,
            quality_score=prev.quality_score,
            cost_score=prev.cost_score,
        )

