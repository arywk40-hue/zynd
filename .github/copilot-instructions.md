# VentureSwarm Copilot Instructions

## Product Scope

VentureSwarm is a hackathon application built on top of ZyndAI, not an implementation of the Zynd platform.

Prioritize only capabilities that materially improve the demo:

- Agent Cards
- Webhooks and agent communication
- Heartbeat and liveness
- Search and discovery
- SDK-managed signed identities
- Monitoring logs and latency metrics
- Reputation scoring
- Optional agent-to-agent messaging
- Optional x402 premium agents

Do not implement platform internals:

- mesh networking
- gossip protocols
- DHT/Kademlia
- registry node architecture
- storage engines or schemas
- HD key derivation
- Ed25519 internals
- deployer internals
- vector search engine internals
- persona runners
- dashboards

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

## Agent Cards

Each agent must expose an application-facing agent card at `/.well-known/agent.json`. The card must include:

- capabilities
- tags
- supported endpoints
- SDK identity/public key
- optional pricing metadata

Use SDK-generated identity/card data where available. Do not hand-roll cryptography.

## Search And Discovery

The orchestrator should express discovery at the application level as:

```python
search_agents(
    query="funding analysis",
    category="startup-intelligence",
    tags=["startup", "funding", "venture-capital"],
    skills=["funding-analysis"],
    protocols=["webhook", "webhook-sync"],
    status="active",
    min_trust_score=0.0,
    entity_type="agent",
    max_results=10,
    federated=True,
    enrich=True,
)
```

Use the official SDK registry search API. Prefer `zyndai_agent.dns_registry.search_agents` when available; on SDK versions where the same real search API is exposed as `search_entities`, use that compatibility path rather than creating fake discovery.

Discovery must remain heartbeat-aware, filter active agents only, enrich Agent Card metadata, and log ranking decisions with trust score, latency, heartbeat freshness, and selected target.

## Monitoring, Logs, And Health

All services must use `rich.logging.RichHandler` through the shared logging setup.

Visible log categories:

- `[Planner]`
- `[Discovery]`
- `[Ranking]`
- `[Selection]`
- `[Dispatch]`
- `[Webhook]`
- `[Response]`
- `[Heartbeat]`
- `[Health]`
- `[Metrics]`
- `[Error]`
- `[Failover]`
- `[Recovery]`
- `[CRASH]`

Every agent `/health` response must stay lightweight and include `status`, `agent_id`, `heartbeat_connected`, `uptime_seconds`, `webhook_requests_total`, `webhook_failures_total`, `average_latency_s`, `success_rate`, and `last_heartbeat`.

The orchestrator should expose aggregate metrics in `/health`: dispatched tasks, failovers, active agents, total runs, average orchestration time, and last error.

## Advanced Prompt Backlog

Keep advanced optional implementation prompts in `venture-swarm/docs/advanced-implementation-prompts.md`.

Only work on those prompts after the core system is stable:

- discovery
- heartbeat
- webhooks
- failover
- observability

The advanced backlog currently covers:

- agent-to-agent messaging
- deeper reputation scoring
- deployer.zynd.ai readiness
- optional x402 premium agents
