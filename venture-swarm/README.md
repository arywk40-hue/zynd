# VentureSwarm

Autonomous Startup Intelligence Swarm using the **real ZyndAI Agent SDK**.

## Architecture

```text
User Query
  ↓
Orchestrator Agent (planner → discovery → ranking → async dispatch → aggregation)
  ↓                             ↘ search_agents(...)
Zynd-compatible Directory (/v1/agents, /v1/search)
  ↑                                      ↓
Agents (trend, funding, competitor, market-gap, risk)
  └─ /webhook/sync + /.well-known/agent.json (SDK runtime)
```

## Tech Stack

- Python 3.12+
- FastAPI
- asyncio
- zyndai-agent
- uvicorn
- pydantic
- rich

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
- `search_agents(...)` for runtime discovery
- `add_message_handler(...)` for inbound message hooks
- `invoke(...)` for per-agent reasoning functions
- `/webhook/sync` for inter-agent request/response messages

## Registration Flow

1. Each agent starts with `AgentConfig` loaded from `agent.config.json`
2. Agent initializes `ZyndAIAgent` (Ed25519 identity + SDK runtime)
3. Agent self-registers to registry via SDK helper (`dns_registry.register_agent`)
4. Agent becomes discoverable via `/v1/search`

## Discovery Flow

1. Orchestrator decomposes query into capability subtasks
2. For each subtask, orchestrator calls `search_agents(...)`
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
PREMIUM_PAYMENT_TOKEN=demo-token uvicorn main:app --port 8001
```

## Demo Script

```bash
curl -s http://localhost:8001/report \
  -H 'content-type: application/json' \
  -d '{"query":"Find a startup opportunity in rural healthcare diagnostics using AI."}' | jq
```

Expected live logs include:

- `[Planner] Breaking task into subtasks...`
- `[Discovery] Searching trend-analysis agents...`
- `[Ranking] Selecting highest reputation agent...`
- `[Dispatch] Sending task to funding-agent...`
- `[Failover] Trying replacement ...` (when needed)
- `[Aggregation] Combining intelligence...`

## Screenshots (placeholders)

- `docs/screenshots/orchestrator.png`
- `docs/screenshots/agents.png`
- `docs/screenshots/report-output.png`

## Hackathon Pitch

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
