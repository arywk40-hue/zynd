from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentReputation(BaseModel):
    latency: float = Field(default=1.0, ge=0.0, description="Observed p95-ish latency in seconds")
    success_rate: float = Field(default=0.95, ge=0.0, le=1.0)
    quality_score: float = Field(default=8.0, ge=0.0, le=10.0)
    cost_score: float = Field(default=0.2, ge=0.0, le=1.0, description="Higher means more expensive")


class AgentCard(BaseModel):
    agent_id: str
    name: str
    version: str = "0.1.0"
    description: str
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    webhook_sync_url: HttpUrl
    health_url: HttpUrl
    reputation: AgentReputation = Field(default_factory=AgentReputation)
    premium_required: bool = False
    premium_cost_usd: float | None = None
    last_seen: datetime = Field(default_factory=utc_now)


class RegisterAgentRequest(BaseModel):
    card: AgentCard
    ttl_s: float = Field(default=30.0, ge=1.0, le=600.0)


class RegisterAgentResponse(BaseModel):
    ok: bool = True


class SearchAgentsResponse(BaseModel):
    keyword: str
    agents: list[AgentCard]


class HeartbeatRequest(BaseModel):
    agent_id: str


class HeartbeatResponse(BaseModel):
    ok: bool = True


class StartupQuery(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


class Subtask(BaseModel):
    id: str
    capability: str
    instruction: str
    keywords: list[str] = Field(default_factory=list)


class CandidateAgent(BaseModel):
    agent_id: str
    name: str
    agent_url: HttpUrl
    fqan: str | None = None
    entity_name: str | None = None
    version: str | None = None
    search_score: float = 0.0
    trust_score: float = 0.0
    rank_score: float = 0.0
    status: str = "unknown"
    last_heartbeat: str | None = None
    freshness_s: float | None = None
    latency_s: float | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    developer_handle: str | None = None
    home_registry: str | None = None
    card: dict[str, Any] | None = None

    @property
    def display_identity(self) -> str:
        if self.fqan:
            return self.fqan
        if self.developer_handle:
            return f"{self.developer_handle}/{self.entity_name or self.name}"
        return self.name


class PlannedTasks(BaseModel):
    query: str
    tasks: list[Subtask]


class AgentTaskRequest(BaseModel):
    task_id: str
    query: str
    instruction: str
    requested_capability: str


class AgentTaskResponse(BaseModel):
    task_id: str
    agent_id: str
    agent_name: str
    capability: str
    data: list[dict[str, Any]]
    notes: list[str] = Field(default_factory=list)


class OpportunitySummary(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=10.0)
    market_saturation: Literal["Low", "Medium", "High"]
    execution_difficulty: Literal["Low", "Medium", "High"]
    monetization: str


class FundingTrajectory(BaseModel):
    round_progression: str
    trend_direction: str
    valuation_direction: str
    investor_quality: str
    summary: str | None = None


class OutcomeForecast(BaseModel):
    breakout: float = Field(ge=0.0, le=1.0)
    steady: float = Field(ge=0.0, le=1.0)
    stall: float = Field(ge=0.0, le=1.0)


class InvestmentScorecard(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    momentum_score: float = Field(ge=0.0, le=10.0)
    moat_score: float = Field(ge=0.0, le=10.0)
    financial_health_score: float = Field(ge=0.0, le=10.0)
    founder_fit_score: float = Field(ge=0.0, le=10.0)
    go_to_market_risk: Literal["Low", "Medium", "High"]
    outcome_forecast: OutcomeForecast
    key_assumptions: list[str] = Field(default_factory=list)


class StartupReport(BaseModel):
    query: str
    top_opportunity: OpportunitySummary
    opportunity_score: float = Field(ge=0.0, le=10.0)
    market_saturation: Literal["Low", "Medium", "High"]
    monetization_potential: Literal["Low", "Medium", "High"]
    execution_difficulty: Literal["Low", "Medium", "High"]
    trends: list[dict[str, Any]] = Field(default_factory=list)
    funding_signals: list[dict[str, Any]] = Field(default_factory=list)
    funding_trajectory: FundingTrajectory | None = None
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    comparables: list[dict[str, Any]] = Field(default_factory=list)
    market_gaps: list[dict[str, Any]] = Field(default_factory=list)
    financial_signals: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    scorecard: InvestmentScorecard | None = None
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
