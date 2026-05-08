# VentureSwarm
Autonomous Startup Intelligence Swarm using a Zynd-style Python SDK (local, runnable).

This is an autonomous AI infrastructure demo: an orchestrator dynamically discovers specialized agent services at runtime, dispatches subtasks in parallel, and aggregates results into a structured startup intelligence report.

## Architecture (runtime)

```text
User Query
  ↓
Orchestrator (planner → discovery → ranking → async dispatch → aggregation)
  ↓                      ↘ (search_agents)
Directory (agent registry)  →  Agents (independent FastAPI services)
  ↑                               └─ /webhook/sync (sync webhook calls)
  └─ agents register + heartbeat
```

## What’s “Zynd” here?
`shared/zynd_sdk.py` implements a minimal Zynd-like SDK interface for this project:
- `ZyndAIAgent(...)` for agent identity + registration
- `search_agents(keyword=...)` for runtime discovery (via the Directory service)

This keeps the demo fully runnable locally while still demonstrating *real runtime discovery* and *decentralized orchestration* (the orchestrator never hardcodes agent URLs).

## Quickstart (Docker)

From `venture-swarm/`:

```bash
docker compose up --build
```

Then call the orchestrator:

```bash
curl -s http://localhost:8001/report \
  -H 'content-type: application/json' \
  -d '{"query":"Find a startup opportunity in rural healthcare diagnostics using AI."}' | jq
```

## Quickstart (Local Python)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Terminal A (Directory):
```bash
uvicorn registry.app:app --port 8000
```

Terminal B (Agents):
```bash
SERVICE_URL=http://localhost:8101 uvicorn agents.trend_agent.agent:app --port 8101
SERVICE_URL=http://localhost:8102 PREMIUM_REQUIRED=true uvicorn agents.funding_agent.agent:app --port 8102
SERVICE_URL=http://localhost:8103 uvicorn agents.competitor_agent.agent:app --port 8103
SERVICE_URL=http://localhost:8104 uvicorn agents.market_gap_agent.agent:app --port 8104
SERVICE_URL=http://localhost:8105 uvicorn agents.risk_agent.agent:app --port 8105
```

Terminal C (Orchestrator):
```bash
PREMIUM_PAYMENT_TOKEN=demo-token uvicorn main:app --port 8001
```

## Demo Flow

The logs show the autonomous pipeline:

- `[Planner] Breaking task into subtasks...`
- `[Discovery] Searching funding-analysis agents...`
- `[Ranking] Selecting highest reputation agent...`
- `[Dispatch] Sending task to market-gap-agent...`
- `[Failover] Trying replacement ...` (if a call fails)
- `[Payment] ... requires payment; retrying with token...` (HTTP 402 simulation)
- `[Aggregation] Combining intelligence...`

## API

- `POST /report`
  - Request: `{ "query": "..." }`
  - Response: structured report:
    - `top_opportunity`
    - `trends`, `funding_signals`, `competitors`, `market_gaps`, `risks`
    - `agent_trace` (latency, failovers, chosen agents)

## Hackathon Pitch

VentureSwarm demonstrates a realistic multi-agent architecture:
- Agents are independent services with explicit capabilities/tags
- Orchestrator performs runtime discovery and reputation-based selection
- Parallel execution with async dispatch + failover
- Optional monetized intelligence via HTTP 402 “premium agent” simulation

## Screenshots

- `docs/screenshots/orchestrator.png` (placeholder)
- `docs/screenshots/agents.png` (placeholder)

