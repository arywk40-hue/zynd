# Advanced Implementation Prompts

These prompts are intentionally scoped as post-core upgrades. Use them only after the current VentureSwarm foundation is stable:

- Agent Cards
- Webhooks and sync communication
- Heartbeat and liveness
- Runtime search and discovery
- Failover
- Monitoring logs and health

Do not let these optional upgrades pull the project into Zynd platform internals. VentureSwarm remains an application built on top of ZyndAI.

## Core Stability Gate

Do not start these prompts until the core system passes:

- `python -m compileall venture-swarm`
- `docker compose config --services`
- all services start without port conflicts
- `/health` returns healthy for directory, orchestrator, and every agent
- `/network` shows active heartbeat-connected agents
- `/report` completes one full startup-intelligence run
- UI renders the latest report without JavaScript errors

If any of these fail, fix the core system first. Advanced features should deepen the demo, not hide broken orchestration.

## 1. Agent-To-Agent Messaging Implementation Prompt

Implement real decentralized agent-to-agent communication inside VentureSwarm using ZyndAI webhook messaging.

Current architecture supports:

- orchestrator to agents

Upgrade the system to support:

- agent to agent
- collaborative swarm execution
- delegated subtasks
- distributed reasoning

The system should feel like a true autonomous swarm network.

### Core Objective

Allow agents to dynamically communicate with other agents during execution.

Examples:

- funding-agent to trend-agent
- competitor-agent to risk-agent
- market-gap-agent to funding-agent

Agents should:

- request additional intelligence
- delegate subtasks
- enrich their own outputs
- collaborate autonomously

### Required Communication Flow

Use real SDK webhook communication with `AgentMessage` and SDK-compatible webhook payloads.

```python
message = AgentMessage(
    content="Analyze healthcare AI funding trends",
    receiver_id="trend-agent-id",
    message_type="query",
    conversation_id="conv_123",
)

response = await agent.x402_processor.post(
    url=f"{target_url}/webhook/sync",
    json=message.to_dict(),
)
```

### Swarm Behavior

Agents must:

- discover compatible agents dynamically
- send requests autonomously
- merge returned intelligence
- continue execution independently

Example workflow:

```text
funding-agent
  -> discovers trend-agent
  -> requests AI healthcare trend data
  -> receives response
  -> combines funding and trend intelligence
```

### Required Features

Implement:

- nested agent communication
- conversation tracking
- distributed subtasks
- async messaging
- failover recovery
- timeout handling

### Conversation State

Preserve:

- `conversation_id`
- `in_reply_to`
- execution lineage

This should allow multi-hop coordination chains.

### Failover Requirements

If a collaborating agent fails:

- rediscover another compatible agent
- retry automatically
- continue execution gracefully

### Logging Requirements

Logs should visibly show swarm coordination:

```text
[Swarm] funding-agent requesting trend intelligence
[Discovery] Found compatible trend-agent
[Coordination] trend-agent processing request
[Response] trend-agent returned market insights
[Merge] funding-agent enriched final output
```

### Most Important

This feature should demonstrate distributed autonomous intelligence.

Do not fake collaboration. Use real inter-agent communication patterns.

## 2. Reputation System Implementation Prompt

Implement an intelligent reputation and ranking system for VentureSwarm agent orchestration.

The orchestrator must dynamically rank discovered agents using runtime performance metrics.

The goal is intelligent autonomous routing.

### Core Objective

When multiple compatible agents are discovered, the orchestrator should automatically select the:

- fastest
- healthiest
- most reliable
- highest quality

agents dynamically.

### Required Metrics

Track per-agent metrics:

```json
{
  "latency": 1.2,
  "success_rate": 0.94,
  "quality_score": 8.7,
  "failure_count": 2,
  "uptime": 86400,
  "heartbeat_connected": true
}
```

### Ranking System

Rank agents using:

- trust score
- latency
- heartbeat health
- success rate
- freshness
- quality score

Agents with lower latency, higher uptime, active heartbeat, and higher success rates should rank higher.

### Orchestrator Requirements

When discovery returns multiple agents:

```python
results = search_agents(
    query="funding analysis",
    enrich=True,
)
```

The orchestrator must:

1. score candidates
2. sort descending
3. select best available agent

### Quality Scoring

Implement lightweight output scoring using:

- response completeness
- execution success
- schema validity
- timeout behavior

Use those signals to update quality score dynamically.

### Failover Intelligence

If a selected agent fails:

- reduce reputation score
- rerank alternatives
- retry automatically

### Logging Requirements

Logs should visibly show ranking decisions:

```text
[Ranking] funding-agent trust=0.92 latency=1.1s success=98%
[Ranking] funding-agent-v2 trust=0.88 latency=0.9s success=94%
[Selection] funding-agent selected
```

### Most Important

The system should feel intelligent: dynamic, adaptive, autonomous, and production-grade.

## 3. Deployer And x402 Premium Agents Implementation Prompt

Implement optional deployment polish and premium-agent support for VentureSwarm using ZyndAI deployment and x402 capabilities.

These are advanced optional features. Do not prioritize them over orchestration, discovery, heartbeat, failover, and distributed coordination.

### Part 1: Deploy Via deployer.zynd.ai

Prepare VentureSwarm agents for deployment on:

```text
deployer.zynd.ai
```

Requirements:

- containerized agents
- public HTTPS URLs
- production-ready startup
- clean health endpoints
- heartbeat connectivity
- structured logs

### Required Deployment Support

Implement:

- Dockerfile per service, if the deployer requires separate service images
- docker-compose support
- environment variable configuration
- graceful startup and shutdown
- public webhook accessibility

Each deployed agent must expose:

- `/webhook`
- `/webhook/sync`
- `/health`
- `/.well-known/agent.json`

### Monitoring Support

Ensure logs work correctly with deployer log streaming.

Use:

- stdout for standard logs
- stderr for exceptions and errors

Log examples:

```text
[Startup] funding-agent deployed successfully
[Heartbeat] connected to registry
[Webhook] received startup-analysis task
```

### Part 2: Optional x402 Premium Agents

Implement optional premium intelligence agents using x402 micropayments.

Examples:

- premium-funding-agent
- premium-market-intelligence-agent
- premium-risk-analysis-agent

Premium agents may provide:

- deeper market analysis
- higher-quality responses
- external API integrations
- advanced startup scoring

### x402 Payment Flow

Use SDK-native x402 support.

The orchestrator should:

1. call premium agent
2. receive HTTP 402 response
3. auto-pay via SDK processor
4. retry automatically

### Optional Premium Routing

Allow orchestrator logic such as:

```text
if startup_score > 8:
  use premium intelligence agents
else:
  use standard agents
```

### Logging Requirements

Show payment and deployment visibility:

```text
[x402] Premium funding-agent requires payment
[x402] Payment completed successfully
[Dispatch] premium-funding-agent processing request
```

### Most Important

These are optional showcase features. Do not overengineer them.

The priority remains:

- discovery
- orchestration
- failover
- distributed coordination
- heartbeat-aware routing
