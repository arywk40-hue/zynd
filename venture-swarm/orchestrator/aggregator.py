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
_FORECAST_BREAKOUT_MIN = 0.1
_FORECAST_BREAKOUT_MAX = 0.75
_FORECAST_STALL_MIN = 0.1
_FORECAST_STALL_MAX = 0.7
_FORECAST_STEADY_MIN = 0.1
_FORECAST_OPPORTUNITY_WEIGHT = 0.6
_FORECAST_FUNDING_WEIGHT = 0.2
_FORECAST_STALL_WEIGHT = 0.5
_FORECAST_STALL_DIFFICULTY_BONUS = 0.2
_FORECAST_STALL_EASY_BONUS = 0.05
_DEFAULT_TREND_ASSUMPTION = "Market momentum holds"
_DEFAULT_GAP_ASSUMPTION = "Focus on a clear underserved segment"
_DEFAULT_FUNDING_ASSUMPTION = "Investor appetite remains"
_DEFAULT_RISK_ASSUMPTION = "Execution risk"


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
    """Blend opportunity and funding into breakout/steady/stall bands with bounded weights."""
    breakout = (opportunity_score / 10.0) * _FORECAST_OPPORTUNITY_WEIGHT + (funding_strength * _FORECAST_FUNDING_WEIGHT)
    breakout = max(_FORECAST_BREAKOUT_MIN, min(_FORECAST_BREAKOUT_MAX, breakout))
    stall = (1.0 - funding_strength) * _FORECAST_STALL_WEIGHT + (
        _FORECAST_STALL_DIFFICULTY_BONUS if difficulty == "High" else _FORECAST_STALL_EASY_BONUS
    )
    stall = max(_FORECAST_STALL_MIN, min(_FORECAST_STALL_MAX, stall))
    steady = max(_FORECAST_STEADY_MIN, 1.0 - breakout - stall)

    total = breakout + steady + stall
    if total <= 0:
        return OutcomeForecast(breakout=0.2, steady=0.6, stall=0.2)

    breakout, steady, stall = (breakout / total, steady / total, stall / total)
    if steady < _FORECAST_STEADY_MIN:
        remainder = 1.0 - _FORECAST_STEADY_MIN
        scale = remainder / max(breakout + stall, 1e-6)
        breakout *= scale
        stall *= scale
        steady = _FORECAST_STEADY_MIN
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
        assumptions.append(f"Trend tailwind: {top_trend.get('trend', _DEFAULT_TREND_ASSUMPTION).strip()}")
    if top_gap:
        assumptions.append(f"Wedge: {top_gap.get('gap', _DEFAULT_GAP_ASSUMPTION).strip()}")
    if top_funding:
        assumptions.append(f"Funding signal: {top_funding.get('signal', _DEFAULT_FUNDING_ASSUMPTION).strip()}")
    if top_risk:
        assumptions.append(f"Primary risk: {top_risk.get('risk', _DEFAULT_RISK_ASSUMPTION).strip()}")
    return [assumption for assumption in assumptions if assumption]


def aggregate(
    *,
    query: str,
    trend: AgentTaskResponse,
    funding: AgentTaskResponse,
    benchmarking: AgentTaskResponse,
    competitors: AgentTaskResponse,
    startup_comparisons: AgentTaskResponse,
    market_gaps: AgentTaskResponse,
    financial_signals: AgentTaskResponse,
    risks: AgentTaskResponse,
    agent_trace: list[dict],
) -> StartupReport:
    log.info("[Aggregation] Combining intelligence...")

    saturation = _pick_market_saturation(competitors.data)
    difficulty = _pick_execution_difficulty(risks.data)

    trend_strength = _average_confidence(trend.data)
    funding_strength = _average_confidence(funding.data)
    financial_strength = _average_confidence(financial_signals.data, default=funding_strength)
    gap_strength = _average_confidence(market_gaps.data)
    comparison_strength = _average_confidence(startup_comparisons.data)

    score_raw = (
        (trend_strength * 10.0 * 0.25)
        + (funding_strength * 10.0 * 0.20)
        + (financial_strength * 10.0 * 0.10)
        + (gap_strength * 10.0 * 0.20)
        + (comparison_strength * 10.0 * 0.05)
        + (_SATURATION_SCORE[saturation] * 0.10)
        + (_DIFFICULTY_SCORE[difficulty] * 0.10)
    )
    opportunity_score = round(min(10.0, max(0.0, score_raw)), 2)

    monetization_signal = (funding_strength + financial_strength) / 2.0
    monetization_potential = "High" if monetization_signal >= 0.75 else "Medium"
    if monetization_signal < 0.6:
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
        benchmarking_comps=benchmarking.data,
        startup_comparisons=startup_comparisons.data,
        market_gaps=market_gaps.data,
        financial_signals=financial_signals.data,
        risks=risks.data,
        scorecard=scorecard,
        agent_trace=agent_trace,
    )
