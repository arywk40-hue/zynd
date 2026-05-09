from __future__ import annotations

from shared.schemas import (
    AgentTaskResponse,
    FundingTrajectory,
    InvestmentScorecard,
    OpportunitySummary,
    OutcomeForecast,
    StartupReport,
)
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


def _average_confidence(items: list[dict], default: float = 0.65) -> float:
    if not items:
        return default
    values = [float(item.get("confidence", default)) for item in items if isinstance(item, dict)]
    return sum(values) / max(1, len(values))


def _funding_trajectory(funding: list[dict]) -> FundingTrajectory | None:
    if not funding:
        return None
    top = funding[0] if isinstance(funding[0], dict) else {}
    return FundingTrajectory(
        round_progression=str(top.get("round_progression") or "Unknown"),
        trend_direction=str(top.get("trend_direction") or "Unknown"),
        valuation_direction=str(top.get("valuation_direction") or "Unknown"),
        investor_quality=str(top.get("investor_quality") or "Unknown"),
        summary=str(top.get("signal") or top.get("why_it_matters") or "Funding narrative unavailable."),
    )


def _forecast_outcomes(opportunity_score: float, funding_strength: float, difficulty: str) -> OutcomeForecast:
    breakout = max(0.1, min(0.75, (opportunity_score / 10.0) * 0.6 + (funding_strength * 0.2)))
    stall = max(0.1, min(0.7, (1.0 - funding_strength) * 0.5 + (0.2 if difficulty == "High" else 0.05)))
    steady = 1.0 - breakout - stall
    if steady < 0.1:
        steady = 0.1
    total = breakout + steady + stall
    breakout, steady, stall = (breakout / total, steady / total, stall / total)
    return OutcomeForecast(breakout=round(breakout, 3), steady=round(steady, 3), stall=round(stall, 3))


def _scorecard_assumptions(
    *,
    top_gap: dict,
    top_trend: dict,
    top_funding: dict,
    top_risk: dict,
) -> list[str]:
    assumptions = []
    if top_trend:
        assumptions.append(f"Trend tailwind: {top_trend.get('trend', 'Market momentum holds').strip()}")
    if top_gap:
        assumptions.append(f"Wedge: {top_gap.get('gap', 'Focus on a clear underserved segment').strip()}")
    if top_funding:
        assumptions.append(f"Funding signal: {top_funding.get('signal', 'Investor appetite remains').strip()}")
    if top_risk:
        assumptions.append(f"Primary risk: {top_risk.get('risk', 'Execution risk').strip()}")
    return [assumption for assumption in assumptions if assumption]


def aggregate(
    *,
    query: str,
    trend: AgentTaskResponse,
    funding: AgentTaskResponse,
    benchmarking: AgentTaskResponse,
    competitors: AgentTaskResponse,
    market_gaps: AgentTaskResponse,
    financial_signals: AgentTaskResponse,
    risks: AgentTaskResponse,
    agent_trace: list[dict],
) -> StartupReport:
    log.info("[Aggregation] Combining intelligence...")

    saturation = _pick_market_saturation(competitors.data)
    difficulty = _pick_execution_difficulty(risks.data)

    trend_strength = _average_confidence(trend.data, default=0.7)
    funding_strength = _average_confidence(funding.data, default=0.7)
    gap_strength = _average_confidence(market_gaps.data, default=0.7)
    financial_strength = _average_confidence(financial_signals.data, default=0.6)

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
    top_trend = trend.data[0] if trend.data else {}
    top_funding = funding.data[0] if funding.data else {}
    top_risk = risks.data[0] if risks.data else {}
    top_opportunity = OpportunitySummary(
        name=str(top_gap.get("gap", "No opportunity identified")).strip()[:80],
        score=opportunity_score,
        market_saturation=saturation,  # type: ignore[arg-type]
        execution_difficulty=difficulty,  # type: ignore[arg-type]
        monetization=str(top_gap.get("monetization", "Not enough data")),
    )

    moat_score = round(_SATURATION_SCORE[saturation], 2)
    momentum_score = round(((trend_strength + funding_strength) / 2.0) * 10.0, 2)
    financial_health_score = round(financial_strength * 10.0, 2)
    founder_fit_score = round(min(10.0, max(0.0, 5.0 + ((gap_strength - 0.5) * 4.0))), 2)
    outcome_forecast = _forecast_outcomes(opportunity_score, funding_strength, difficulty)
    overall_score = round(
        min(
            10.0,
            max(
                0.0,
                (momentum_score * 0.30)
                + (moat_score * 0.20)
                + (financial_health_score * 0.30)
                + (founder_fit_score * 0.20),
            ),
        ),
        2,
    )
    scorecard = InvestmentScorecard(
        overall_score=overall_score,
        momentum_score=momentum_score,
        moat_score=moat_score,
        financial_health_score=financial_health_score,
        founder_fit_score=founder_fit_score,
        go_to_market_risk=difficulty,  # type: ignore[arg-type]
        outcome_forecast=outcome_forecast,
        key_assumptions=_scorecard_assumptions(
            top_gap=top_gap,
            top_trend=top_trend,
            top_funding=top_funding,
            top_risk=top_risk,
        ),
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
        funding_trajectory=_funding_trajectory(funding.data),
        competitors=competitors.data,
        comparables=benchmarking.data,
        market_gaps=market_gaps.data,
        financial_signals=financial_signals.data,
        risks=risks.data,
        scorecard=scorecard,
        agent_trace=agent_trace,
    )
