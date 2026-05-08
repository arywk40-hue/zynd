from __future__ import annotations

import uuid

from shared.schemas import PlannedTasks, Subtask
from shared.utils import get_logger


log = get_logger("Planner")


def plan(query: str) -> PlannedTasks:
    log.info("[Planner] Breaking task into subtasks...")

    tasks = [
        Subtask(
            id=str(uuid.uuid4()),
            capability="trend-analysis",
            instruction="Identify 3-5 relevant market and technology trends affecting this idea.",
            keywords=["trend-analysis", "startup-trends", "ai-market-research"],
        ),
        Subtask(
            id=str(uuid.uuid4()),
            capability="funding-analysis",
            instruction="Infer funding signals, likely buyer, and how VCs would view this opportunity.",
            keywords=["funding-analysis", "vc-research", "investment-signals"],
        ),
        Subtask(
            id=str(uuid.uuid4()),
            capability="competitor-analysis",
            instruction="Assess competitive landscape and saturation; suggest differentiation angles.",
            keywords=["competitor-analysis", "saturation-analysis"],
        ),
        Subtask(
            id=str(uuid.uuid4()),
            capability="market-gap-analysis",
            instruction="Find underserved segments and propose the best wedge entry point.",
            keywords=["market-gap-analysis", "underserved-market-detection"],
        ),
        Subtask(
            id=str(uuid.uuid4()),
            capability="regulatory-risk-analysis",
            instruction="List key regulatory and technical feasibility risks with mitigations.",
            keywords=["regulatory-risk-analysis", "technical-feasibility-analysis"],
        ),
    ]

    return PlannedTasks(query=query, tasks=tasks)

