from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from zyndai_agent.message import AgentMessage

from orchestrator.reputation import ReputationStore
from shared.schemas import AgentTaskResponse, CandidateAgent, Subtask
from shared.utils import get_logger, timed


log = get_logger("Dispatch")


@dataclass(frozen=True)
class DispatchResult:
    response: AgentTaskResponse
    used_agent: CandidateAgent
    latency_s: float
    failovers: int


async def _call_agent(*, sender_id: str, candidate: CandidateAgent, task: Subtask, query: str, payment_token: str | None) -> AgentTaskResponse:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if payment_token:
        headers["X-Payment-Token"] = payment_token

    msg = AgentMessage(
        content=query,
        sender_id=sender_id,
        message_type="query",
        metadata={
            "task_id": task.id,
            "instruction": task.instruction,
            "requested_capability": task.capability,
        },
    )

    sync_url = f"{str(candidate.agent_url).rstrip('/')}/webhook/sync"
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as client:
        r = await client.post(sync_url, json=msg.to_dict(), headers=headers)
        if r.status_code == 402:
            raise httpx.HTTPStatusError("payment required", request=r.request, response=r)
        r.raise_for_status()
        return AgentTaskResponse.model_validate(r.json())


async def dispatch_with_failover(
    *,
    sender_id: str,
    task: Subtask,
    query: str,
    candidates: list[CandidateAgent],
    store: ReputationStore,
    payment_token: str | None,
) -> DispatchResult:
    if not candidates:
        raise RuntimeError(f"no candidates for capability={task.capability}")

    last_exc: Exception | None = None
    failovers = 0

    for idx, candidate in enumerate(candidates):
        if idx == 0:
            log.info("[Dispatch] Sending task to %s...", candidate.name)
        else:
            log.warning("[Failover] Trying replacement %s...", candidate.name)
            failovers += 1

        token_for_attempt: str | None = None
        try:
            tr = await timed(
                _call_agent(
                    sender_id=sender_id,
                    candidate=candidate,
                    task=task,
                    query=query,
                    payment_token=token_for_attempt,
                )
            )
            store.update_observation(candidate.agent_id, latency_s=tr.latency_s, success=True)
            return DispatchResult(response=tr.value, used_agent=candidate, latency_s=tr.latency_s, failovers=failovers)
        except httpx.HTTPStatusError as e:
            store.update_observation(candidate.agent_id, latency_s=2.5, success=False)
            last_exc = e
            if e.response is not None and e.response.status_code == 402 and payment_token:
                log.warning("[Payment] %s requires payment; retrying with token...", candidate.name)
                try:
                    tr = await timed(
                        _call_agent(
                            sender_id=sender_id,
                            candidate=candidate,
                            task=task,
                            query=query,
                            payment_token=payment_token,
                        )
                    )
                    store.update_observation(candidate.agent_id, latency_s=tr.latency_s, success=True)
                    return DispatchResult(response=tr.value, used_agent=candidate, latency_s=tr.latency_s, failovers=failovers)
                except Exception as e2:  # noqa: BLE001
                    last_exc = e2
                    continue
            continue
        except (httpx.TransportError, asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            store.update_observation(candidate.agent_id, latency_s=3.0, success=False)
            last_exc = e
            continue

    raise RuntimeError(f"all candidates failed for capability={task.capability}: {last_exc}")
