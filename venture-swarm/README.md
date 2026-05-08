# VentureSwarm

Autonomous Startup Intelligence Swarm using the **real ZyndAI Agent SDK**.

## Architecture

```text
User Query
  ↓
Orchestrator Agent (planner → discovery → ranking → async dispatch → aggregation)
  ↓                             ↘ search_agents(..., federated=True, enrich=True)
Zynd-compatible Directory (/v1/agents, /v1/search)
  ↑                                      ↓
Agents (trend, funding, competitor, market-gap, risk)
  └─ /webhook/sync + /.well-known/agent.json (SDK runtime)
```

## Hackathon Scope

VentureSwarm is an application built on top of ZyndAI. It intentionally focuses on the Zynd capabilities that make the demo stronger:

- Agent Cards for discoverable capabilities, tags, endpoints, identity, and optional pricing
- Webhooks for sync and async agent communication
- Heartbeat and liveness for active/offline routing
- Search and discovery for dynamic orchestration
- SDK-managed signed identities and verified communication
- Rich logs for dispatch, heartbeat, failover, latency, and active agent counts

It does not implement Zynd platform internals such as mesh networking, gossip, DHT, registry node architecture, storage engines, HD key derivation, Ed25519 internals, deployer internals, or search engine internals.

## Tech Stack

- Python 3.12+
- FastAPI
- asyncio
- zyndai-agent[heartbeat]
- uvicorn
- pydantic
- rich
- websockets

## Project Structure

```text
venture-swarm/
├── orchestrator/
│   ├── planner.py
│   ├── dispatcher.py
│   ├── aggregator.py
│   ├── reputation.py
│   ├── orchestrator.py
│   └── orchestrator_agent.py
├── agents/
│   ├── trend_agent/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── agent.config.json
│   ├── funding_agent/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── agent.config.json
│   ├── competitor_agent/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── agent.config.json
│   ├── market_gap_agent/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   └── agent.config.json
│   └── risk_agent/
│       ├── agent.py
│       ├── prompts.py
│       └── agent.config.json
├── registry/
│   └── app.py
├── shared/
│   ├── schemas.py
│   ├── utils.py
│   ├── logging_config.py
│   ├── zynd_runtime.py
│   └── config.py
├── docs/
│   └── advanced-implementation-prompts.md
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── main.py
```

## SDK Usage

The implementation uses real SDK APIs/classes:

- `from zyndai_agent.agent import AgentConfig, ZyndAIAgent`
- `from zyndai_agent.message import AgentMessage`
- SDK runtime startup for registration, A2A sidecar, and heartbeat
- Zynd registry search for heartbeat-aware runtime discovery
- `invoke(...)` for per-agent reasoning functions
- `/webhook/sync` for inter-agent request/response messages

## Agent Cards

Each agent exposes:

- `/.well-known/agent.json`
- `agent_id` and `public_key`
- `name`, `description`, `category`, and searchable `tags`
- `capabilities`
- supported endpoints: `invoke`, `invoke_async`, `health`, and `agent_card`
- optional `pricing` metadata for premium agents
- `status`, `updated_at`, and SDK-signed `signature`

The SDK identity/keypair signs the card. Clients can fetch the card before invoking an agent, verify the signature, then call the advertised `invoke` or `invoke_async` endpoint.

## Registration Flow

1. Each agent starts with `AgentConfig` loaded from `agent.config.json`
2. Agent initializes `ZyndAIAgent` (Ed25519 identity + SDK runtime)
3. Agent self-registers through the SDK runtime
4. Agent becomes discoverable via `/v1/search`
5. Agent keeps liveness active through the SDK WebSocket heartbeat

## Discovery Flow

1. Orchestrator decomposes query into capability subtasks
2. For each subtask, orchestrator calls the Zynd SDK registry search with:
   - `category="startup-intelligence"`
   - capability-specific `query`, `tags`, and `skills`
   - `protocols=["webhook", "webhook-sync"]`
   - `status="active"`
   - `federated=True`
   - `enrich=True`
3. Candidates are ranked by blended score:
   - trust score
   - heartbeat availability and freshness
   - response latency
   - success rate
   - quality score
   - discovery score

## Dispatch, Parallelism, and Failover

- Dispatch uses `AgentMessage` payloads to each candidate’s `/webhook/sync`
- All subtasks execute concurrently with `await asyncio.gather(...)`
- If an agent fails, orchestrator retries with the next ranked candidate
- If 402 is returned (premium funding agent), orchestrator retries with payment token
- `/webhook` accepts async fire-and-forget messages with `202 Accepted`
- `/health` is checked before dispatch so unhealthy agents are skipped
- Outbound calls use the SDK x402 processor and SDK `AgentMessage` structure

## Heartbeat And Liveness

- Agents start the ZyndAI SDK runtime on startup, which starts the SDK WebSocket heartbeat.
- `/health` includes `agent_id` and `heartbeat_connected`.
- Discovery requests active agents only and ignores offline registry entries.
- Shutdown calls the SDK runtime stop path so heartbeat sessions close cleanly.

## Monitoring Logs

The runtime logs show:

- `[Planner]` task decomposition
- `[Heartbeat]` connection, active, reconnecting, and shutdown events
- `[Discovery]` runtime search filters and active-agent candidate counts
- `[Ranking]` trust, latency, heartbeat freshness, and score
- `[Selection]` chosen target agent
- `[Dispatch]` selected target agents
- `[Webhook]` outgoing and incoming agent messages
- `[Failover]` replacement discovery
- `[Recovery]` retry/rerouting decisions
- `[CRASH]` heartbeat disconnects and unreachable services
- `[Health]` startup, health checks, and clean shutdown
- `[Response]` per-agent latency
- `[Metrics]` active agents, average latency, failures, success rate, and orchestration time

Each agent `/health` response includes:

- `status`
- `agent_id`
- `heartbeat_connected`
- `uptime_seconds`
- `webhook_requests_total`
- `webhook_failures_total`
- `average_latency_s`
- `success_rate`
- `last_heartbeat`

The orchestrator `/health` response includes:

- `tasks_dispatched`
- `failovers_triggered`
- `active_agents`
- `orchestrations_total`
- `average_orchestration_time_s`
- `last_error`

## Output Shape

`POST /report` returns structured startup intelligence:

- `top_opportunity`
- `opportunity_score`
- `market_saturation`
- `monetization_potential`
- `execution_difficulty`
- `trends`
- `funding_signals`
- `competitors`
- `market_gaps`
- `risks`
- `agent_trace`

## Setup

### Docker (recommended)

```bash
cd venture-swarm
docker compose up --build
```

### Local

```bash
cd venture-swarm
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For live LLM-backed agent outputs, edit `.env` and set one provider:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Supported providers are `openai`, `groq`, `gemini`, `anthropic`, `mistral`, and `cerebras`. Keep `LLM_PROVIDER=none` to run the distributed infrastructure without live model calls.

For OpenAI-compatible gateways, set `OPENAI_BASE_URL` and `OPENAI_MODEL` with `LLM_PROVIDER=openai`.

Run services:

```bash
uvicorn registry.app:app --port 8000
SERVICE_URL=http://localhost:8101 uvicorn agents.trend_agent.agent:app --port 8101
SERVICE_URL=http://localhost:8102 PREMIUM_REQUIRED=true uvicorn agents.funding_agent.agent:app --port 8102
SERVICE_URL=http://localhost:8103 uvicorn agents.competitor_agent.agent:app --port 8103
SERVICE_URL=http://localhost:8104 uvicorn agents.market_gap_agent.agent:app --port 8104
SERVICE_URL=http://localhost:8105 uvicorn agents.risk_agent.agent:app --port 8105
PREMIUM_PAYMENT_TOKEN=$PREMIUM_PAYMENT_TOKEN uvicorn main:app --port 8001
```

## API Call

```bash
curl -s http://localhost:8001/report \
  -H 'content-type: application/json' \
  -d '{"query":"<startup intelligence query>"}' | jq
```

## Positioning

VentureSwarm is a decentralized startup-intelligence infrastructure layer:

- autonomous orchestration (not chatbot UX)
- dynamic runtime discovery
- capability-based parallel delegation
- resilience via failover and retry
- structured, decision-grade startup outputs

## Advanced Prompts

Post-core implementation prompts live in `docs/advanced-implementation-prompts.md`:

- agent-to-agent messaging
- richer reputation scoring
- deployer.zynd.ai polish
- optional x402 premium agents

Treat these as later upgrades after discovery, heartbeat, webhooks, failover, and observability are stable.

## Troubleshooting

- **No agents discovered**: verify all five agents are running and registered (`/v1/search` on directory)
- **402 errors**: set `PREMIUM_PAYMENT_TOKEN` in orchestrator environment
- **Registry mismatch**: ensure all services point to same `DIRECTORY_URL` / `ZYND_REGISTRY_URL`
- **Port conflicts**: check service ports `8000, 8001, 8101-8105`
