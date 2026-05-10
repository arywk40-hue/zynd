# Architecture: Zynd Autonomous Startup Intelligence Swarm

## System Overview
The Autonomous Startup Intelligence Swarm is a multi-tier, decentralized AI ecosystem. Rather than relying on a single monolithic LLM, this system utilizes an **Orchestrator Agent** to dynamically discover, hire, and manage a network of specialized sub-agents using the Zynd Python SDK. 

This project is an application built on top of ZyndAI, not a reimplementation of Zynd infrastructure. It demonstrates autonomous networking, parallel execution, heartbeat-aware routing, and AI-to-AI service coordination through the SDK capabilities that matter for the hackathon demo.

---

## High-Level Data Flow

```text
                               [ USER INPUT ]
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │    ORCHESTRATOR AGENT       │
                      │ (Task Planner & Dispatcher) │
                      └─────────────────────────────┘
                                     │
             ┌───────────────────────┼───────────────────────┐
             │ (Dynamic Discovery via Zynd registry search)   │
             ▼                       ▼                       ▼
   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
   │ TREND RESEARCH   │    │  COMPETITOR AI   │    │  FUNDING SYSTEM  │
   │      AGENT       │    │      AGENT       │    │      AGENT       │
   │ (Apify Search)   │    │  (Market Gaps)   │    │ (Premium / USDC) │
   └──────────────────┘    └──────────────────┘    └──────────────────┘
             │                       │                       │
             └───────────────────────┼───────────────────────┘
                                     │ (Parallel Webhook Sync)
                                     ▼
                      ┌─────────────────────────────┐
                      │     AGGREGATION ENGINE      │
                      │   (Synthesis & Scoring)     │
                      └─────────────────────────────┘
                                     │
                                     ▼
                          [ FINAL STARTUP REPORT ]

```

---

## Core Components

### 1. The Orchestrator (The Brain)

* **Role:** Decomposes user requests, handles Zynd agent discovery, manages parallel async execution, and synthesizes the final output.
* **Tech:** Python, FastAPI, `asyncio`, ZyndAI SDK runtime.

### 2. The Agent Swarm (The Workers)

Each agent is registered as an independent entity on the Zynd network using `ZyndAIAgent(...)`.

* **Trend Research Agent:** Uses Apify Google Search context to identify market momentum.
* **Funding Intelligence Agent:** Uses Apify Google News context for venture funding signals and can be gated behind HTTP 402 Payment Required.
* **Benchmarking Agent:** Builds comparable startup sets and requests financial overlays from the financial signals agent.
* **Financial Signals Agent:** Estimates burn/runway, margin, and unit economics proxies.
* **Competitor Analysis Agent:** Analyzes saturation and existing solutions.
* **Startup Compare Agent:** Compares similar startups for funding, traction, profit upside, and loss/downside patterns.
* **Market Gap Agent:** Finds underserved segments and user pain points.
* **Risk Analysis Agent:** Evaluates regulatory, privacy, legal, and technical barriers.

---

## Zynd SDK Integration Points

This project heavily leverages the unique features of the Zynd SDK to prove the viability of a decentralized AI network:

1. **Identity & Registration:** Every agent boots up with a distinct Ed25519 identity and registers an Entity Card containing its capabilities and tags.
2. **Dynamic Discovery:** The Orchestrator does not hardcode worker IPs. It uses the Zynd SDK registry search API with capability queries, tags, skills, active heartbeat status, `federated=True`, and `enrich=True` to find workers at runtime.
3. **Agent-to-Agent Comms:** All task delegation occurs via `/webhook/sync`.
4. **AI Economy:** Uses HTTP 402 Payment Required as the payment-required signal for premium data agents.

---

## Explicit Non-Goals

VentureSwarm does not implement mesh networking, gossip, DHT/Kademlia, registry node internals, storage engines, HD key derivation, Ed25519 internals, deployer internals, or custom search engine infrastructure. Those are Zynd platform concerns; this repo focuses on agent cards, webhooks, heartbeat, discovery, signed identities, reputation, and orchestration logs.

---

## Tech Stack

* **Infrastructure:** Zynd Python SDK
* **Backend:** Python 3.12+, FastAPI (for agent endpoints)
* **Concurrency:** `asyncio`
* **LLM Providers:** OpenAI / Groq / Gemini / Anthropic / Mistral / Cerebras
* **Tooling:** Apify (Google Search, Google News, Reddit scrapers)

---

## Directory Structure

```text
venture-swarm/
├── orchestrator/
│   ├── planner.py              # Breaks down the user prompt
│   ├── discovery.py            # Heartbeat-aware Zynd registry search
│   ├── dispatcher.py           # Webhook dispatch, retries, x402 fallback
│   ├── reputation.py           # Latency, success, and quality scoring
│   ├── orchestrator.py         # Runtime orchestration
│   ├── orchestrator_agent.py   # API-facing wrapper
│   └── aggregator.py           # Scorecard, forecast, and synthesis
├── agents/
│   ├── trend_agent/
│   ├── funding_agent/
│   ├── benchmarking_agent/
│   ├── competitor_agent/
│   ├── startup_compare_agent/
│   ├── market_gap_agent/
│   ├── financial_signals_agent/
│   └── risk_agent/
├── registry/
│   └── app.py                  # Local SDK-compatible directory for demos
├── shared/
│   ├── schemas.py              # Pydantic models for strict JSON outputs
│   ├── llm.py                  # Live LLM provider calls + retries
│   ├── apify_tools.py          # Real web-data grounding
│   ├── zynd_runtime.py         # SDK runtime compatibility helpers
│   ├── config.py
│   └── utils.py
├── docs/
│   ├── advanced-implementation-prompts.md
│   └── zns-deployment.md
├── main.py                     # UI/API entry point
├── docker-compose.yml
└── requirements.txt

```
