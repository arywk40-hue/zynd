import unittest

from orchestrator.aggregator import (
    _coerce_confidence,
    _forecast_outcomes,
    _funding_trajectory,
    aggregate,
)
from shared.schemas import AgentTaskResponse


def _response(capability: str, data: list[dict]) -> AgentTaskResponse:
    return AgentTaskResponse(
        task_id=f"task-{capability}",
        agent_id=f"agent-{capability}",
        agent_name=f"{capability}-agent",
        capability=capability,
        data=data,
    )


class AggregatorTests(unittest.TestCase):
    def test_coerce_confidence_normalizes_and_clamps(self) -> None:
        self.assertEqual(_coerce_confidence(None, 0.65), 0.65)
        self.assertEqual(_coerce_confidence("bad", 0.65), 0.65)
        self.assertEqual(_coerce_confidence(7, 0.65), 0.7)
        self.assertEqual(_coerce_confidence(20, 0.65), 1.0)
        self.assertEqual(_coerce_confidence(-5, 0.65), 0.0)

    def test_forecast_outcomes_are_bounded_and_normalized(self) -> None:
        forecast = _forecast_outcomes(opportunity_score=10.0, funding_strength=1.0, difficulty="Low")

        self.assertAlmostEqual(forecast.breakout + forecast.steady + forecast.stall, 1.0, places=3)
        self.assertGreaterEqual(forecast.steady, 0.1)
        self.assertGreaterEqual(forecast.breakout, 0.0)
        self.assertGreaterEqual(forecast.stall, 0.0)

    def test_funding_trajectory_fallbacks(self) -> None:
        trajectory = _funding_trajectory([{}])

        self.assertIsNotNone(trajectory)
        assert trajectory is not None
        self.assertEqual(trajectory.round_progression, "Unknown")
        self.assertEqual(trajectory.summary, "Funding narrative unavailable.")

    def test_aggregate_builds_report_with_scorecard(self) -> None:
        trend = _response("trend-analysis", [{"trend": "AI copilots", "confidence": 0.9}])
        funding = _response("funding-analysis", [{"signal": "Strong seed appetite", "confidence": 0.8}])
        benchmarking = _response("benchmarking-analysis", [{"company": "Comp A", "confidence": 0.7}])
        competitors = _response("competitor-analysis", [{"name": "Comp B", "saturation": "Medium", "confidence": 0.6}])
        startup_comparisons = _response("startup-comparison", [{"name": "Analog Co", "confidence": 0.7}])
        market_gaps = _response("market-gap-analysis", [{"gap": "SMB compliance automation", "monetization": "B2B SaaS", "confidence": 0.85}])
        financial_signals = _response("financial-signal-analysis", [{"burn": "moderate", "confidence": 0.75}])
        risks = _response("risk-analysis", [{"risk": "Regulatory shifts", "severity": "Medium", "confidence": 0.5}])

        report = aggregate(
            query="startup idea",
            trend=trend,
            funding=funding,
            benchmarking=benchmarking,
            competitors=competitors,
            startup_comparisons=startup_comparisons,
            market_gaps=market_gaps,
            financial_signals=financial_signals,
            risks=risks,
            agent_trace=[{"agent_id": "trend-agent", "status": "ok"}],
        )

        self.assertEqual(report.query, "startup idea")
        self.assertEqual(report.top_opportunity.name, "SMB compliance automation")
        self.assertEqual(report.market_saturation, "Medium")
        self.assertEqual(report.execution_difficulty, "Medium")
        self.assertIsNotNone(report.scorecard)
        self.assertIsNotNone(report.funding_trajectory)
        self.assertGreaterEqual(report.opportunity_score, 0.0)
        self.assertLessEqual(report.opportunity_score, 10.0)

    def test_aggregate_handles_empty_inputs(self) -> None:
        empty = _response("empty", [])

        report = aggregate(
            query="idea",
            trend=empty,
            funding=empty,
            benchmarking=empty,
            competitors=empty,
            startup_comparisons=empty,
            market_gaps=empty,
            financial_signals=empty,
            risks=empty,
            agent_trace=[],
        )

        self.assertEqual(report.top_opportunity.name, "No opportunity identified")
        self.assertIsNone(report.funding_trajectory)
        self.assertIn(report.monetization_potential, {"Low", "Medium", "High"})


if __name__ == "__main__":
    unittest.main()
