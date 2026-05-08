# VentureSwarm

Autonomous Startup Intelligence Swarm using the **real ZyndAI Agent SDK**.

## Architecture

```text
User Query
  ↓
Orchestrator Agent (planner → discovery → ranking → async dispatch → aggregation)
  ↓                             ↘ heartbeat-aware registry search
Zynd-compatible Directory (/v1/agents, /v1/search)
  ↑                                      ↓
Agents (trend, funding, competitor, market-gap, risk)
  └─ /webhook/sync + /.well-known/agent.json (SDK runtime)
```

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
│   └── config.py
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
- `dns_registry.search_entities(..., status="active")` for runtime discovery
- `invoke(...)` for per-agent reasoning functions
- `/webhook/sync` for inter-agent request/response messages

## Registration Flow

1. Each agent starts with `AgentConfig` loaded from `agent.config.json`
2. Agent initializes `ZyndAIAgent` (Ed25519 identity + SDK runtime)
3. Agent self-registers through the SDK runtime
4. Agent becomes discoverable via `/v1/search`
5. Agent keeps liveness active through the SDK WebSocket heartbeat

## Discovery Flow

1. Orchestrator decomposes query into capability subtasks
2. For each subtask, orchestrator searches for active registry entries
3. Candidates are ranked by blended score:
   - discovery score
   - latency
   - success rate
   - quality score
   - reliability

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
```

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

## Troubleshooting

- **No agents discovered**: verify all five agents are running and registered (`/v1/search` on directory)
- **402 errors**: set `PREMIUM_PAYMENT_TOKEN` in orchestrator environment
- **Registry mismatch**: ensure all services point to same `DIRECTORY_URL` / `ZYND_REGISTRY_URL`
- **Port conflicts**: check service ports `8000, 8001, 8101-8105`
