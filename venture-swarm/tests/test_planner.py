import unittest
import uuid

from orchestrator.planner import plan


class PlannerTests(unittest.TestCase):
    def test_plan_returns_expected_capabilities_and_unique_ids(self) -> None:
        query = "ai workflow assistant for legal teams"

        planned = plan(query)

        self.assertEqual(planned.query, query)
        self.assertEqual(len(planned.tasks), 8)

        expected_capabilities = [
            "trend-analysis",
            "funding-analysis",
            "benchmarking-analysis",
            "competitor-analysis",
            "startup-comparison",
            "market-gap-analysis",
            "financial-signal-analysis",
            "risk-analysis",
        ]
        self.assertEqual([task.capability for task in planned.tasks], expected_capabilities)

        task_ids = [task.id for task in planned.tasks]
        self.assertEqual(len(task_ids), len(set(task_ids)))
        for task in planned.tasks:
            uuid.UUID(task.id)
            self.assertTrue(task.instruction)
            self.assertTrue(task.keywords)


if __name__ == "__main__":
    unittest.main()
