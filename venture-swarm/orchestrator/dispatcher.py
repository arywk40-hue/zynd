from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx
import requests
from zyndai_agent.agent import ZyndAIAgent
from zyndai_agent.message import AgentMessage

from orchestrator.reputation import ReputationStore
from shared.llm import required_fields_for_capability
from shared.schemas import AgentTaskResponse, CandidateAgent, Subtask
from shared.utils import get_logger, timed


log = get_logger("Dispatch")
_DEFAULT_SCHEMA_QUALITY = 0.75


def _x402_enabled() -> bool:
    return os.getenv("X402_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _dispatch_timeout_s() -> float:
    raw = os.getenv("AGENT_DISPATCH_TIMEOUT_S", "24")
    try:
        return max(3.0, float(raw))
    except ValueError:
        return 24.0


def _candidate_requires_payment(candidate: CandidateAgent) -> bool:
    card = candidate.card or {}
    payment = card.get("payment") or {}
    return bool(card.get("pricing") or payment.get("premium_required"))


def _schema_quality(capability: str, data: list[dict]) -> float:
    required = required_fields_for_capability(capability)
    if not required:
        return _DEFAULT_SCHEMA_QUALITY
    if not data:
        return 0.0

    def _has_value(value: object) -> bool:
        return value not in ("", None) and value not in ([], {}, ())

    scored: list[float] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        present = sum(
            1 for field in required if _has_value(item.get(field))
        )
        scored.append(present / len(required))
    if not scored:
        return 0.0
    return sum(scored) / len(scored)


def _record_quality(
    *,
    store: ReputationStore,
    candidate: CandidateAgent,
    capability: str,
    latency_s: float,
    response: AgentTaskResponse,
) -> None:
    quality = _schema_quality(capability, response.data)
    store.update_observation(candidate.agent_id, latency_s=latency_s, success=True, quality_score=quality)
    log.info("[Metrics] %s schema_quality=%.2f", candidate.display_identity, quality)


@dataclass(frozen=True)
class DispatchResult:
    response: AgentTaskResponse
    used_agent: CandidateAgent
    latency_s: float
    failovers: int


class AgentDispatchHTTPError(RuntimeError):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"agent returned HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


async def _candidate_healthy(candidate: CandidateAgent) -> bool:
    if candidate.status not in {"active", "online"}:
        log.warning("[Health] %s skipped because status=%s", candidate.display_identity, candidate.status)
        log.warning("[Recovery] Removing %s from active pool", candidate.display_identity)
        return False
    if candidate.freshness_s is not None and candidate.freshness_s > 120:
        log.warning("[Health] %s skipped because heartbeat is stale %.1fs", candidate.display_identity, candidate.freshness_s)
        log.warning("[CRASH] %s failed heartbeat freshness check", candidate.display_identity)
        log.warning("[Recovery] Removing %s from active pool", candidate.display_identity)
        return False

    health_url = f"{str(candidate.agent_url).rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            response = await client.get(health_url)
        if response.status_code != 200:
            log.warning("[Health] %s returned HTTP %s", candidate.display_identity, response.status_code)
            return False
        payload = response.json()
        heartbeat_ok = payload.get("heartbeat_connected")
        is_healthy = payload.get("status") in {"healthy", "ok"} and heartbeat_ok is not False
        if not is_healthy:
            log.warning("[Health] %s unhealthy: %s", candidate.display_identity, payload)
            log.warning("[CRASH] %s became unhealthy or disconnected", candidate.display_identity)
            log.warning("[Recovery] Removing %s from active pool", candidate.display_identity)
        return bool(is_healthy)
    except Exception as e:  # noqa: BLE001
        log.warning("[Error] %s health check failed: %s", candidate.display_identity, e)
        log.warning("[CRASH] %s unreachable during health check", candidate.display_identity)
        log.warning("[Recovery] Removing %s from active pool", candidate.display_identity)
        return False


async def _call_agent(
    *,
    sender_agent: ZyndAIAgent,
    candidate: CandidateAgent,
    task: Subtask,
    query: str,
    payment_token: str | None,
    conversation_id: str,
    in_reply_to: str | None,
) -> AgentTaskResponse:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if payment_token:
        headers["X-Payment-Token"] = payment_token

    msg = AgentMessage(
        content=query,
        sender_id=sender_agent.entity_id,
        sender_public_key=sender_agent.keypair.public_key_string,
        receiver_id=candidate.agent_id,
        message_type="query",
        conversation_id=conversation_id,
        in_reply_to=in_reply_to,
        metadata={
            "task_id": task.id,
            "instruction": task.instruction,
            "requested_capability": task.capability,
        },
    )

    sync_url = f"{str(candidate.agent_url).rstrip('/')}/webhook/sync"
    log.info("[Webhook] POST %s (%s)", sync_url, candidate.display_identity)

    def _post():
        timeout_s = _dispatch_timeout_s()
        if _x402_enabled():
            return sender_agent.x402_processor.post(sync_url, json=msg.to_dict(), headers=headers, timeout=timeout_s)
        if payment_token:
            return requests.post(sync_url, json=msg.to_dict(), headers=headers, timeout=timeout_s)
        try:
            return sender_agent.x402_processor.post(sync_url, json=msg.to_dict(), headers=headers, timeout=timeout_s)
        except Exception as e:  # noqa: BLE001
            if "Invalid payment required response" in str(e):
                return requests.post(sync_url, json=msg.to_dict(), headers=headers, timeout=timeout_s)
            raise

    try:
        response = await asyncio.to_thread(_post)
    except requests.HTTPError as e:
        if e.response is not None:
            raise AgentDispatchHTTPError(e.response.status_code, e.response.text) from e
        raise
    if response.status_code == 200:
        return AgentTaskResponse.model_validate(response.json())
    if response.status_code == 202:
        raise AgentDispatchHTTPError(response.status_code, "sync endpoint returned async accepted")
    if response.status_code in {400, 401, 402, 403, 500}:
        raise AgentDispatchHTTPError(response.status_code, response.text)
    raise AgentDispatchHTTPError(response.status_code, response.text)


async def dispatch_with_failover(
    *,
    sender_agent: ZyndAIAgent,
    task: Subtask,
    query: str,
    candidates: list[CandidateAgent],
    store: ReputationStore,
    payment_token: str | None,
    conversation_id: str,
    in_reply_to: str | None = None,
) -> DispatchResult:
    if not candidates:
        raise RuntimeError(f"no candidates for capability={task.capability}")

    last_exc: Exception | None = None
    failovers = 0

    for idx, candidate in enumerate(candidates):
        if idx == 0:
            log.info("[Dispatch] Sending task to %s...", candidate.display_identity)
        else:
            log.warning("[Failover] Trying replacement %s...", candidate.display_identity)
            log.warning("[Resolution] Resolving latest %s version", candidate.entity_name or task.capability)
            failovers += 1

        if _candidate_requires_payment(candidate):
            log.info("[x402] Premium candidate detected: %s", candidate.display_identity)

        if not await _candidate_healthy(candidate):
            store.update_observation(candidate.agent_id, latency_s=3.0, success=False)
            log.warning("[Failover] Discovering replacement %s agent", task.capability)
            continue

        token_for_attempt: str | None = None
        try:
            tr = await timed(
                _call_agent(
                    sender_agent=sender_agent,
                    candidate=candidate,
                    task=task,
                    query=query,
                    payment_token=token_for_attempt,
                    conversation_id=conversation_id,
                    in_reply_to=in_reply_to,
                )
            )
            _record_quality(
                store=store,
                candidate=candidate,
                capability=task.capability,
                latency_s=tr.latency_s,
                response=tr.value,
            )
            if _candidate_requires_payment(candidate) and _x402_enabled():
                log.info("[x402] Payment successful")
            return DispatchResult(response=tr.value, used_agent=candidate, latency_s=tr.latency_s, failovers=failovers)
        except AgentDispatchHTTPError as e:
            store.update_observation(candidate.agent_id, latency_s=2.5, success=False)
            last_exc = e
            if e.status_code == 402 and payment_token:
                log.warning("[x402] %s requires payment; retrying with configured payment token...", candidate.display_identity)
                try:
                    tr = await timed(
                        _call_agent(
                            sender_agent=sender_agent,
                            candidate=candidate,
                            task=task,
                            query=query,
                            payment_token=payment_token,
                            conversation_id=conversation_id,
                            in_reply_to=in_reply_to,
                        )
                    )
                    _record_quality(
                        store=store,
                        candidate=candidate,
                        capability=task.capability,
                        latency_s=tr.latency_s,
                        response=tr.value,
                    )
                    return DispatchResult(response=tr.value, used_agent=candidate, latency_s=tr.latency_s, failovers=failovers)
                except Exception as e2:  # noqa: BLE001
                    last_exc = e2
                    continue
            log.warning("[Error] %s webhook failed: %s", candidate.display_identity, e)
            log.warning("[Failover] Discovering replacement...")
            continue
        except (httpx.TransportError, asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
            store.update_observation(candidate.agent_id, latency_s=3.0, success=False)
            last_exc = e
            log.warning("[Error] %s timeout or transport failure: %s", candidate.display_identity, e)
            log.warning("[Failover] Discovering replacement...")
            continue

    raise RuntimeError(f"all candidates failed for capability={task.capability}: {last_exc}")
