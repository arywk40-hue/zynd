from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from orchestrator.reputation import ReputationStore
from shared.schemas import AgentCard, AgentTaskRequest, AgentTaskResponse, Subtask
from shared.utils import get_logger, timed


log = get_logger("Dispatch")


@dataclass(frozen=True)
class DispatchResult:
    response: AgentTaskResponse
    used_agent: AgentCard
    latency_s: float
    failovers: int


async def _call_agent(
    *,
    card: AgentCard,
    task: Subtask,
    query: str,
    payment_token: str | None,
) -> AgentTaskResponse:
    headers: dict[str, str] = {}
    if payment_token:
        headers["X-Payment-Token"] = payment_token

    payload = AgentTaskRequest(
        task_id=task.id,
        query=query,
        instruction=task.instruction,
        requested_capability=task.capability,
    ).model_dump(mode="json")

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.post(str(card.webhook_sync_url), json=payload, headers=headers)
        if r.status_code == 402:
            raise httpx.HTTPStatusError("payment required", request=r.request, response=r)
        r.raise_for_status()
        return AgentTaskResponse.model_validate(r.json())


async def dispatch_with_failover(
    *,
    task: Subtask,
    query: str,
    candidates: list[AgentCard],
    store: ReputationStore,
    payment_token: str | None,
) -> DispatchResult:
    if not candidates:
        raise RuntimeError(f"no candidates for capability={task.capability}")

    last_exc: Exception | None = None
    failovers = 0

    for idx, card in enumerate(candidates):
        if idx == 0:
            log.info("[Dispatch] Sending task to %s...", card.name)
        else:
            log.warning("[Failover] Trying replacement %s...", card.name)
            failovers += 1

        # For premium agents we intentionally start without a token to demonstrate 402 + retry.
        token_for_attempt: str | None = None
        try:
            tr = await timed(_call_agent(card=card, task=task, query=query, payment_token=token_for_attempt))
            store.update_observation(card, latency_s=tr.latency_s, success=True)
            return DispatchResult(response=tr.value, used_agent=card, latency_s=tr.latency_s, failovers=failovers)
        except httpx.HTTPStatusError as e:
            store.update_observation(card, latency_s=2.5, success=False)
            last_exc = e
            if e.response is not None and e.response.status_code == 402:
                if payment_token:
                    log.warning("[Payment] %s requires payment; retrying with token...", card.name)
                    try:
                        tr = await timed(_call_agent(card=card, task=task, query=query, payment_token=payment_token))
                        store.update_observation(card, latency_s=tr.latency_s, success=True)
                        return DispatchResult(
                            response=tr.value, used_agent=card, latency_s=tr.latency_s, failovers=failovers
                        )
                    except Exception as e2:  # noqa: BLE001
                        last_exc = e2
                        continue
                else:
                    log.warning("[Payment] %s requires payment, but no token configured.", card.name)
            continue
        except (httpx.TransportError, asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            store.update_observation(card, latency_s=3.0, success=False)
            last_exc = e
            continue

    raise RuntimeError(f"all candidates failed for capability={task.capability}: {last_exc}")
