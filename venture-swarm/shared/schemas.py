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


class StartupReport(BaseModel):
    query: str
    top_opportunity: OpportunitySummary
    opportunity_score: float = Field(ge=0.0, le=10.0)
    market_saturation: Literal["Low", "Medium", "High"]
    monetization_potential: Literal["Low", "Medium", "High"]
    execution_difficulty: Literal["Low", "Medium", "High"]
    trends: list[dict[str, Any]] = Field(default_factory=list)
    funding_signals: list[dict[str, Any]] = Field(default_factory=list)
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    market_gaps: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)

