import unittest

from orchestrator.reputation import ReputationStore
from shared.schemas import CandidateAgent


def _candidate(**overrides):
    data = {
        "agent_id": "agent-1",
        "name": "trend-agent",
        "agent_url": "https://example.com",
        "search_score": 0.55,
        "trust_score": 0.75,
        "status": "active",
        "freshness_s": 30.0,
        "latency_s": 0.4,
    }
    data.update(overrides)
    return CandidateAgent(**data)


class ReputationStoreTests(unittest.TestCase):
    def test_score_uses_default_observation_for_unknown_agent(self) -> None:
        store = ReputationStore()

        score = store.score("unknown-agent", discovery_score=0.8)

        self.assertAlmostEqual(score, 0.824, places=3)

    def test_score_candidate_blends_candidate_and_observed_signals(self) -> None:
        store = ReputationStore()
        store.update_observation("agent-1", latency_s=2.0, success=True, quality_score=0.9)

        score_with_negative_latency = store.score_candidate(_candidate(latency_s=-1.0, freshness_s=600.0, status="active"))
        score_with_zero_latency = store.score_candidate(_candidate(latency_s=0.0, freshness_s=600.0, status="active"))

        self.assertAlmostEqual(score_with_negative_latency, score_with_zero_latency, places=6)
        self.assertGreaterEqual(score_with_negative_latency, 0.0)
        self.assertLessEqual(score_with_negative_latency, 1.0)
        self.assertGreater(score_with_negative_latency, 0.5)

    def test_update_observation_tracks_failures_and_clamps_quality(self) -> None:
        store = ReputationStore()

        store.update_observation("agent-1", latency_s=2.0, success=False, quality_score=2.5)
        obs = store.observation_for("agent-1")

        self.assertAlmostEqual(obs.latency_s, 1.6, places=3)
        self.assertEqual(obs.failure_count, 1)
        self.assertEqual(obs.observations_total, 1)
        self.assertAlmostEqual(obs.success_rate, 0.81, places=2)
        self.assertAlmostEqual(obs.quality_score, 0.874, places=3)

    def test_success_rate_and_snapshot(self) -> None:
        store = ReputationStore()
        self.assertEqual(store.success_rate(), 1.0)

        store.update_observation("a", latency_s=1.0, success=True, quality_score=0.8)
        store.update_observation("b", latency_s=1.0, success=False, quality_score=0.8)

        self.assertLess(store.success_rate(), 1.0)
        snapshot = store.snapshot()
        self.assertIn("a", snapshot)
        self.assertIn("b", snapshot)
        self.assertEqual(snapshot["a"]["observations_total"], 1)
        self.assertGreaterEqual(snapshot["a"]["uptime"], 0.0)


if __name__ == "__main__":
    unittest.main()
