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
