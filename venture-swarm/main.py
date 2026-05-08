from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from orchestrator.orchestrator_agent import VentureSwarmOrchestrator
from shared.config import get_settings
from shared.schemas import StartupQuery, StartupReport
from shared.utils import get_logger, setup_logging
from shared.zynd_runtime import install_shutdown_handlers


settings = get_settings()
setup_logging(settings.log_level)
log = get_logger("main")

orchestrator = VentureSwarmOrchestrator(settings)
install_shutdown_handlers("venture-swarm-orchestrator", orchestrator.stop)


@asynccontextmanager
async def lifespan(_: FastAPI):
    orchestrator.start()
    try:
        yield
    finally:
        orchestrator.stop()


app = FastAPI(title="VentureSwarm Orchestrator", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VentureSwarm</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f7f4;
      color: #1e2525;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; }
    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 22px;
      border-bottom: 1px solid #d9ddd5;
      padding-bottom: 18px;
    }
    h1 { margin: 0; font-size: clamp(1.65rem, 3vw, 2.4rem); letter-spacing: 0; }
    .status { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .pill {
      border: 1px solid #bdc7bd;
      background: #ffffff;
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 0.85rem;
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(280px, 0.82fr) minmax(420px, 1.18fr);
      gap: 18px;
      align-items: start;
    }
    section {
      border: 1px solid #d3d8d0;
      background: #ffffff;
      border-radius: 8px;
      padding: 18px;
    }
    h2 { margin: 0 0 12px; font-size: 1rem; letter-spacing: 0; }
    label { display: block; font-size: 0.88rem; margin-bottom: 8px; color: #4b5551; }
    textarea {
      width: 100%;
      min-height: 150px;
      resize: vertical;
      border: 1px solid #bcc6bd;
      border-radius: 8px;
      padding: 12px;
      font: inherit;
      line-height: 1.45;
    }
    button {
      margin-top: 12px;
      appearance: none;
      border: 0;
      border-radius: 8px;
      background: #146b5d;
      color: white;
      font-weight: 700;
      padding: 11px 14px;
      cursor: pointer;
    }
    button:disabled { opacity: 0.62; cursor: wait; }
    .map-shell {
      position: relative;
      min-height: 560px;
      border: 1px solid #d7ded6;
      border-radius: 8px;
      background: linear-gradient(180deg, #fbfcfa 0%, #f3f6f2 100%);
      overflow: hidden;
      padding: 18px;
    }
    .map-graph {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(190px, 0.82fr) minmax(0, 1fr);
      grid-template-rows: repeat(3, minmax(128px, auto));
      gap: 18px;
      min-height: 520px;
      align-items: stretch;
    }
    .connectors {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
    }
    .connectors line {
      stroke: #a9b8b0;
      stroke-width: 2;
      stroke-linecap: round;
    }
    .node {
      position: relative;
      min-width: 0;
      border: 1px solid #ccd5ce;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.96);
      padding: 13px;
      box-shadow: 0 10px 22px rgba(35, 45, 42, 0.08);
      overflow-wrap: anywhere;
    }
    .node h3 {
      margin: 0 0 8px;
      font-size: 0.9rem;
      letter-spacing: 0;
    }
    .node p {
      margin: 0;
      color: #34413d;
      font-size: 0.9rem;
      line-height: 1.4;
    }
    .node ul {
      margin: 8px 0 0;
      padding-left: 18px;
      color: #34413d;
      font-size: 0.84rem;
      line-height: 1.36;
    }
    .node li + li { margin-top: 5px; }
    .center-node {
      grid-column: 2;
      grid-row: 2;
      align-self: center;
      background: #124e46;
      border-color: #0b3a34;
      color: #ffffff;
      min-height: 172px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    .center-node h3,
    .center-node p { color: #ffffff; }
    .center-node .score {
      margin-top: 12px;
      display: inline-flex;
      width: fit-content;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.15);
      padding: 6px 9px;
      font-size: 0.82rem;
    }
    .profit { grid-column: 1; grid-row: 1; border-top: 4px solid #24785f; }
    .people { grid-column: 3; grid-row: 1; border-top: 4px solid #385f9d; }
    .target { grid-column: 1; grid-row: 3; border-top: 4px solid #8355a1; }
    .loss { grid-column: 3; grid-row: 3; border-top: 4px solid #a36b27; }
    .disadvantages {
      grid-column: 3;
      grid-row: 2;
      border-top: 4px solid #a13f3f;
      align-self: center;
    }
    details {
      margin-top: 14px;
      border: 1px solid #d7ded6;
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
    }
    summary {
      cursor: pointer;
      font-weight: 700;
      color: #24302d;
    }
    pre {
      margin: 12px 0 0;
      white-space: pre-wrap;
      word-break: break-word;
      font: 0.82rem ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: #101615;
      color: #edf5ee;
      border-radius: 8px;
      padding: 14px;
      max-height: 360px;
      overflow: auto;
    }
    .agents {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .agent {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      padding: 10px 0;
      border-top: 1px solid #eef0ec;
      font-size: 0.9rem;
    }
    .muted { color: #5c6863; font-size: 0.82rem; }
    @media (max-width: 820px) {
      header { align-items: start; flex-direction: column; }
      .status { justify-content: flex-start; }
      .grid { grid-template-columns: 1fr; }
      .map-shell { min-height: unset; }
      .map-graph {
        display: flex;
        flex-direction: column;
        min-height: unset;
      }
      .center-node { order: -1; min-height: unset; }
      .connectors { display: none; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>VentureSwarm</h1>
        <div class="muted">Autonomous startup intelligence network</div>
      </div>
      <div class="status">
        <span class="pill" id="health">health: checking</span>
        <span class="pill" id="active">active agents: checking</span>
      </div>
    </header>

    <div class="grid">
      <section>
        <h2>Startup Query</h2>
        <label for="query">Ask the swarm for a startup opportunity report.</label>
        <textarea id="query">Find a startup opportunity in rural healthcare diagnostics using AI for India and emerging markets.</textarea>
        <button id="run" type="button">Run Report</button>
        <div class="agents" id="agents"></div>
      </section>

      <section>
        <h2>Live Output</h2>
        <div class="map-shell">
          <svg class="connectors" id="connectors"></svg>
          <div class="map-graph" id="map"></div>
        </div>
        <details>
          <summary>Raw Agent Report</summary>
          <pre id="output">Waiting for a query...</pre>
        </details>
      </section>
    </div>
  </main>

  <script>
    const healthEl = document.getElementById("health");
    const activeEl = document.getElementById("active");
    const agentsEl = document.getElementById("agents");
    const mapEl = document.getElementById("map");
    const connectorsEl = document.getElementById("connectors");
    const outputEl = document.getElementById("output");
    const runEl = document.getElementById("run");
    const queryEl = document.getElementById("query");

    function renderJSON(value) {
      outputEl.textContent = JSON.stringify(value, null, 2);
    }

    function firstText(items, keys, fallback) {
      for (const item of items || []) {
        for (const key of keys) {
          if (item && item[key]) return String(item[key]);
        }
      }
      return fallback;
    }

    function uniqueList(items, key, fallback) {
      const values = [];
      const seen = new Set();
      for (const item of items || []) {
        const value = item && item[key] ? String(item[key]) : "";
        if (value && !seen.has(value)) {
          seen.add(value);
          values.push(value);
        }
      }
      return values.length ? values.slice(0, 3) : [fallback];
    }

    function listHTML(values) {
      return `<ul>${values.map((value) => `<li>${escapeHTML(value)}</li>`).join("")}</ul>`;
    }

    function escapeHTML(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function renderBranchMap(report) {
      const idea = report.top_opportunity || {};
      const profitSignals = uniqueList(report.funding_signals, "signal", report.monetization_potential || "Not enough data");
      const people = uniqueList(report.market_gaps, "target_user", "Early adopters not identified yet");
      const targets = [
        firstText(report.market_gaps, ["gap"], "Market gap not identified yet"),
        firstText(report.trends, ["trend"], "Trend signal not identified yet")
      ];
      const disadvantages = uniqueList(report.risks, "risk", "Main disadvantages not identified yet");
      const losses = [
        `Market saturation: ${report.market_saturation || "Unknown"}`,
        `Execution difficulty: ${report.execution_difficulty || "Unknown"}`,
        `Highest visible risk: ${firstText(report.risks, ["severity"], "Unknown")}`
      ];

      mapEl.innerHTML = `
        <article class="node center-node" data-node="center">
          <h3>Startup Idea</h3>
          <p>${escapeHTML(idea.name || "No opportunity selected yet")}</p>
          <span class="score">score ${Number(report.opportunity_score || idea.score || 0).toFixed(2)} / 10</span>
        </article>
        <article class="node profit" data-node="branch">
          <h3>Profit</h3>
          <p>${escapeHTML(report.monetization_potential || "Unknown")} monetization potential</p>
          ${listHTML(profitSignals)}
        </article>
        <article class="node people" data-node="branch">
          <h3>People</h3>
          <p>Primary users and buyers.</p>
          ${listHTML(people)}
        </article>
        <article class="node target" data-node="branch">
          <h3>Target</h3>
          ${listHTML(targets)}
        </article>
        <article class="node disadvantages" data-node="branch">
          <h3>Disadvantages</h3>
          ${listHTML(disadvantages)}
        </article>
        <article class="node loss" data-node="branch">
          <h3>Loss</h3>
          ${listHTML(losses)}
        </article>
      `;
      requestAnimationFrame(drawConnectors);
    }

    function renderEmptyMap(message) {
      mapEl.innerHTML = `
        <article class="node center-node" data-node="center">
          <h3>Startup Idea</h3>
          <p>${escapeHTML(message)}</p>
          <span class="score">waiting</span>
        </article>
      `;
      connectorsEl.innerHTML = "";
    }

    function drawConnectors() {
      const center = mapEl.querySelector("[data-node='center']");
      const branches = mapEl.querySelectorAll("[data-node='branch']");
      if (!center || !branches.length) {
        connectorsEl.innerHTML = "";
        return;
      }
      const shellRect = connectorsEl.getBoundingClientRect();
      const centerRect = center.getBoundingClientRect();
      const startX = centerRect.left + centerRect.width / 2 - shellRect.left;
      const startY = centerRect.top + centerRect.height / 2 - shellRect.top;
      connectorsEl.innerHTML = "";
      for (const branch of branches) {
        const rect = branch.getBoundingClientRect();
        const endX = rect.left + rect.width / 2 - shellRect.left;
        const endY = rect.top + rect.height / 2 - shellRect.top;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", startX);
        line.setAttribute("y1", startY);
        line.setAttribute("x2", endX);
        line.setAttribute("y2", endY);
        connectorsEl.append(line);
      }
    }

    async function refreshNetwork() {
      const [health, network] = await Promise.all([
        fetch("/health").then((res) => res.json()),
        fetch("/network").then((res) => res.json())
      ]);
      healthEl.textContent = `health: ${health.status}`;
      activeEl.textContent = `active agents: ${network.active_agents}`;
      agentsEl.innerHTML = "";
      for (const agent of network.agents || []) {
        const row = document.createElement("div");
        row.className = "agent";
        const left = document.createElement("div");
        left.innerHTML = `<strong>${agent.name}</strong><div class="muted">${(agent.capabilities || []).join(", ") || agent.category || "agent"}</div>`;
        const right = document.createElement("div");
        right.className = "muted";
        right.textContent = agent.status;
        row.append(left, right);
        agentsEl.append(row);
      }
    }

    async function runReport() {
      runEl.disabled = true;
      renderEmptyMap("Running distributed report...");
      outputEl.textContent = "Running distributed report...";
      try {
        const response = await fetch("/report", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({query: queryEl.value})
        });
        const payload = await response.json();
        renderBranchMap(payload);
        renderJSON(payload);
        await refreshNetwork();
      } catch (error) {
        renderEmptyMap(String(error));
        outputEl.textContent = String(error);
      } finally {
        runEl.disabled = false;
      }
    }

    runEl.addEventListener("click", runReport);
    window.addEventListener("resize", drawConnectors);
    renderEmptyMap("Waiting for a query...");
    refreshNetwork().catch((error) => {
      healthEl.textContent = "health: unavailable";
      activeEl.textContent = "active agents: unavailable";
      renderEmptyMap(String(error));
      outputEl.textContent = String(error);
    });
  </script>
</body>
</html>
"""


@app.get("/health")
async def health() -> dict:
    return orchestrator.health()


@app.get("/network")
async def network() -> dict:
    return await orchestrator.network()


@app.post("/report", response_model=StartupReport)
async def report(req: StartupQuery) -> StartupReport:
    log.info("[Orchestrator] Received query: %s", req.query)
    return await orchestrator.run(req.query)


def _cli() -> int:
    if len(sys.argv) < 2:
        print("Usage: python main.py \"your startup research query\"")
        return 2
    query = " ".join(sys.argv[1:])
    # Minimal CLI runner: requires directory + agents running separately.
    import asyncio

    rep = asyncio.run(orchestrator.run(query))
    print(json.dumps(rep.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(_cli())
