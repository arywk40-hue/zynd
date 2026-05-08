# VentureSwarm Copilot Instructions

## Heartbeat And Liveness Requirements

Implement ZyndAI heartbeat and liveness through the official SDK runtime.

Do not create custom agent heartbeat clients, heartbeat signing, reconnect loops, signature verification, or active/offline state managers in agent or orchestrator code. The SDK runtime owns WebSocket heartbeat behavior, signed heartbeat payloads, reconnect behavior, exponential backoff, and heartbeat shutdown.

Required dependencies:

```txt
zyndai-agent[heartbeat]
websockets>=14.0
```

Agent startup must initialize `ZyndAIAgent` from `AgentConfig` and start the SDK runtime. In SDK versions that expose `agent.run()`, call `run()`. In SDK versions that expose `agent.start()`, call `start()`. Heartbeat must begin as part of that SDK runtime startup.

Each agent `/health` endpoint must expose heartbeat state:

```python
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent_id": agent.agent_id,
        "heartbeat_connected": agent.heartbeat_client.is_connected(),
    }
```

If the installed SDK exposes heartbeat state through a different runtime property, adapt the health endpoint without implementing a custom heartbeat loop.

Graceful shutdown must stop the SDK heartbeat cleanly by calling the SDK runtime shutdown method, such as `agent.stop_heartbeat()` or `agent.stop()`.

The orchestrator must use heartbeat-aware discovery:

- request active agents only from the registry
- ignore offline or stale agents
- rediscover a compatible active agent when dispatch fails
- retry the task after failover

Console logs should make heartbeat activity visible, for example:

```text
[Heartbeat] trend-agent connected to registry
[Heartbeat] funding-agent active
[Heartbeat] competitor-agent reconnecting...
[Heartbeat] competitor-agent restored
[Discovery] Filtering active agents only
```

The project should demonstrate distributed liveness behavior that is automatic, resilient, visible in logs, integrated into discovery and failover, and production-clean.

## Webhooks And Agent Communication

Use the ZyndAI SDK message model for inter-agent communication. Do not create simplified message objects or fake transport payloads.

Required agent endpoints:

- `POST /webhook` for async fire-and-forget task delivery
- `POST /webhook/sync` for blocking request-response task delivery
- `GET /health` for health and liveness reporting

The orchestrator should primarily use `/webhook/sync` for structured startup intelligence tasks and must send `zyndai_agent.message.AgentMessage` payloads with:

- `sender_id`
- `sender_public_key`
- `receiver_id`
- `conversation_id`
- `message_type`
- `metadata`
- `in_reply_to`

Agents must register a real SDK message handler with `agent.on_message(...)` and route webhook requests through that SDK-backed handler logic. Keep sync and async webhook handling consistent with the same registered handler.

The orchestrator must:

- verify `/health` before dispatch
- avoid unhealthy agents
- dispatch subtasks concurrently with `asyncio.gather(...)`
- call agents through `agent.x402_processor.post(...)`
- rediscover and retry when an agent times out, returns unhealthy, fails a webhook response, or disconnects heartbeat

The communication layer should log incoming requests, outgoing requests, sync versus async calls, retries, failovers, and response latency.
