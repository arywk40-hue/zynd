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
   │ (Web/Scraping)   │    │  (Market Gaps)   │    │ (Premium / USDC) │
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
* **Tech:** Python, `asyncio`, LangGraph (optional for strict routing).

### 2. The Agent Swarm (The Workers)

Each agent is registered as an independent entity on the Zynd network using `ZyndAIAgent(...)`.

* **Trend Research Agent:** Utilizes Tavily/SerpAPI to find market momentum.
* **Competitor Analysis Agent:** Analyzes saturation and existing solutions.
* **Funding Intelligence Agent:** Tracks funding data and can be gated behind a payment flow signaled via HTTP 402 Payment Required.
* **Risk Analysis Agent:** Evaluates regulatory and technical barriers.

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
* **Backend:** Python 3.11+, FastAPI (for agent endpoints)
* **Concurrency:** `asyncio`
* **LLM Providers:** Gemini / OpenAI / Groq (mixed model routing based on agent needs)
* **Tooling:** Tavily Search API, Firecrawl

---

## Directory Structure

```text
zynd-swarm/
├── orchestrator/
│   ├── planner.py         # Breaks down the user prompt
│   ├── discovery.py       # Interacts with Zynd registry search
│   └── aggregator.py      # Combines the sub-agent responses
├── agents/
│   ├── trend_agent/       # FastAPI app + Zynd SDK init
│   ├── competitor_agent/  # FastAPI app + Zynd SDK init
│   └── funding_agent/     # FastAPI app + Zynd SDK init
├── core/
│   ├── prompts.py         # System instructions for all models
│   └── schemas.py         # Pydantic models for strict JSON outputs
├── main.py                # CLI/API entry point for the user
└── requirements.txt

```
