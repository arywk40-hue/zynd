from __future__ import annotations

from shared.schemas import AgentTaskResponse, OpportunitySummary, StartupReport
from shared.utils import get_logger


log = get_logger("Aggregation")


_SATURATION_SCORE = {"Low": 8.5, "Medium": 6.0, "High": 3.5}
_DIFFICULTY_SCORE = {"Low": 8.5, "Medium": 6.0, "High": 3.5}


def _pick_market_saturation(competitors: list[dict]) -> str:
    # Pick the worst saturation reported.
    levels = [c.get("saturation", "Medium") for c in competitors]
    if "High" in levels:
        return "High"
    if "Low" in levels and "Medium" not in levels:
        return "Low"
    return "Medium"


def _pick_execution_difficulty(risks: list[dict]) -> str:
    if any(r.get("severity") == "High" for r in risks):
        return "High"
    if any(r.get("severity") == "Medium" for r in risks):
        return "Medium"
    return "Low"


def aggregate(
    *,
    query: str,
    trend: AgentTaskResponse,
    funding: AgentTaskResponse,
    competitors: AgentTaskResponse,
    market_gaps: AgentTaskResponse,
    risks: AgentTaskResponse,
    agent_trace: list[dict],
) -> StartupReport:
    log.info("[Aggregation] Combining intelligence...")

    saturation = _pick_market_saturation(competitors.data)
    difficulty = _pick_execution_difficulty(risks.data)

    trend_strength = sum(float(t.get("confidence", 0.7)) for t in trend.data) / max(1, len(trend.data))
    funding_strength = sum(float(s.get("confidence", 0.7)) for s in funding.data) / max(1, len(funding.data))
    gap_strength = sum(float(g.get("confidence", 0.7)) for g in market_gaps.data) / max(1, len(market_gaps.data))

    score_raw = (
        (trend_strength * 10.0 * 0.30)
        + (funding_strength * 10.0 * 0.25)
        + (gap_strength * 10.0 * 0.25)
        + (_SATURATION_SCORE[saturation] * 0.10)
        + (_DIFFICULTY_SCORE[difficulty] * 0.10)
    )
    opportunity_score = round(min(10.0, max(0.0, score_raw)), 2)

    monetization_potential = "High" if funding_strength >= 0.75 else "Medium"
    if funding_strength < 0.6:
        monetization_potential = "Low"

    top_gap = market_gaps.data[0] if market_gaps.data else {}
    top_opportunity = OpportunitySummary(
        name=str(top_gap.get("gap", "No opportunity identified")).strip()[:80],
        score=opportunity_score,
        market_saturation=saturation,  # type: ignore[arg-type]
        execution_difficulty=difficulty,  # type: ignore[arg-type]
        monetization=str(top_gap.get("monetization", "Not enough data")),
    )

    return StartupReport(
        query=query,
        top_opportunity=top_opportunity,
        opportunity_score=opportunity_score,
        market_saturation=saturation,  # type: ignore[arg-type]
        monetization_potential=monetization_potential,  # type: ignore[arg-type]
        execution_difficulty=difficulty,  # type: ignore[arg-type]
        trends=trend.data,
        funding_signals=funding.data,
        competitors=competitors.data,
        market_gaps=market_gaps.data,
        risks=risks.data,
        agent_trace=agent_trace,
    )
