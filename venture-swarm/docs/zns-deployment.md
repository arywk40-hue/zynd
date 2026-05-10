# ZNS Deployment Checklist

Use this when moving VentureSwarm from local Docker Compose to public ZNS discovery.

## Goal

Every service must have a public HTTPS identity that other agents can discover and invoke through ZNS:

- `/.well-known/agent.json`
- `/health`
- `/webhook`
- `/webhook/sync`

## Registry And Namespace

Set these on every agent and the orchestrator:

```bash
ZYND_REGISTRY_URL=https://zns01.zynd.ai
DIRECTORY_URL=https://zns01.zynd.ai
ZNS_ROOT=zns01.zynd.ai
ZNS_DEVELOPER_HANDLE=venture-swarm
```

## Public Service URLs

Set `SERVICE_URL` per public agent:

```bash
SERVICE_URL=https://trend-agent.your-host.example
SERVICE_URL=https://funding-agent.your-host.example
SERVICE_URL=https://benchmarking-agent.your-host.example
SERVICE_URL=https://competitor-agent.your-host.example
SERVICE_URL=https://startup-compare-agent.your-host.example
SERVICE_URL=https://market-gap-agent.your-host.example
SERVICE_URL=https://financial-signals-agent.your-host.example
SERVICE_URL=https://risk-agent.your-host.example
```

The orchestrator should also have a public URL if you want users or other agents to call it directly.

## Persistent Identity

Persist `.keys` or the SDK keypair path for every deployed service. Do not let deployment rebuilds erase key material unless you intentionally want to rotate identities.

Recommended:

```bash
ZYND_AGENT_KEYPAIR_PATH=/persistent/zynd/agent.json
```

Why this matters:

- Agent IDs remain stable.
- ZNS names keep resolving to the same identity.
- Agent cards keep signing with the expected key.
- x402 wallet addresses do not rotate unexpectedly.

## Live Data Secrets

For the strongest demo:

```bash
APIFY_ENABLED=true
APIFY_API_TOKEN=<secret>
APIFY_MAX_ITEMS=3
APIFY_TIMEOUT_S=20
APIFY_CACHE_TTL_S=600

LLM_PROVIDER=groq
GROQ_API_KEY=<secret>
GROQ_MODEL=llama-3.3-70b-versatile
LLM_MAX_ITEMS=3
LLM_TIMEOUT_S=20
```

Use secrets/variables in your host. Do not commit real keys.

## Verify Each Agent

For every public agent:

```bash
curl -s https://<agent-host>/health
curl -s https://<agent-host>/.well-known/agent.json
```

Expected:

- `status` is `healthy`
- `heartbeat_connected` is `true`
- `agent_id` exists
- agent card includes the public `invoke`, `invoke_async`, `health`, and `agent_card` URLs

## Verify Network Discovery

On the orchestrator:

```bash
curl -s https://<orchestrator-host>/network
```

Expected:

- `active_agents` is at least `8`
- all agents show `status=active` or `online`
- FQANs use `zns01.zynd.ai/venture-swarm/<agent-name>`

## Demo Query

```bash
curl -s https://<orchestrator-host>/report \
  -H 'content-type: application/json' \
  -d '{"query":"AI-powered diagnostics for rural healthcare in India and Southeast Asia"}'
```

Expected:

- non-empty `trends`, `funding_signals`, `market_gaps`, and `risks`
- `scorecard` exists
- `agent_trace` shows real selected agents
- logs show `[Discovery]`, `[Dispatch]`, `[Webhook]`, `[Response]`, and `[Aggregation]`
