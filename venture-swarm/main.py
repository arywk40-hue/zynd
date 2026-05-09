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
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0e1114;
      color: #eef4ef;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 20% 0%, rgba(55, 119, 103, 0.28), transparent 34%),
        radial-gradient(circle at 90% 18%, rgba(77, 90, 150, 0.24), transparent 30%),
        #0e1114;
    }
    main {
      width: min(1480px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 22px;
      border-bottom: 1px solid rgba(232, 239, 235, 0.12);
      padding-bottom: 18px;
    }
    h1 { margin: 0; font-size: clamp(1.65rem, 3vw, 2.4rem); letter-spacing: 0; }
    .status { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .pill {
      border: 1px solid rgba(196, 210, 203, 0.22);
      background: rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 0.85rem;
      white-space: nowrap;
      color: #dbe8e0;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(290px, 0.64fr) minmax(640px, 1.36fr);
      gap: 18px;
      align-items: start;
    }
    section {
      border: 1px solid rgba(203, 216, 208, 0.16);
      background: rgba(15, 19, 22, 0.82);
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 24px 54px rgba(0, 0, 0, 0.26);
    }
    h2 { margin: 0 0 12px; font-size: 1rem; letter-spacing: 0; }
    label { display: block; font-size: 0.88rem; margin-bottom: 8px; color: #aebeb6; }
    textarea {
      width: 100%;
      min-height: 150px;
      resize: vertical;
      border: 1px solid rgba(199, 214, 206, 0.18);
      border-radius: 8px;
      padding: 12px;
      font: inherit;
      line-height: 1.45;
      background: #11181b;
      color: #edf5ee;
    }
    button {
      margin-top: 12px;
      appearance: none;
      border: 0;
      border-radius: 8px;
      background: #24a07f;
      color: white;
      font-weight: 700;
      padding: 11px 14px;
      cursor: pointer;
    }
    button:disabled { opacity: 0.62; cursor: wait; }
    .loop-panel {
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid rgba(232, 240, 236, 0.1);
    }
    .loop-panel h3 {
      margin: 0 0 8px;
      font-size: 0.95rem;
      letter-spacing: 0;
    }
    .loop-panel p {
      margin: 0;
      color: #aebeb6;
      font-size: 0.86rem;
      line-height: 1.42;
    }
    .loop-actions,
    .idea-options {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .loop-actions {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .loop-actions button,
    .idea-options button {
      margin: 0;
      border: 1px solid rgba(216, 228, 222, 0.16);
      background: #1d262b;
      color: #dfe9e4;
      text-align: left;
      font-size: 0.82rem;
      line-height: 1.25;
      font-weight: 700;
      min-height: 42px;
    }
    .idea-options button {
      background: rgba(36, 160, 127, 0.12);
    }
    .output-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .map-toolbar {
      display: inline-flex;
      gap: 8px;
      align-items: center;
    }
    .map-toolbar button {
      width: 34px;
      height: 34px;
      margin: 0;
      padding: 0;
      border-radius: 8px;
      background: #1d262b;
      border: 1px solid rgba(216, 228, 222, 0.16);
      color: #dfe9e4;
      font-size: 1rem;
    }
    .map-shell {
      position: relative;
      min-height: 640px;
      border: 1px solid rgba(217, 228, 222, 0.14);
      border-radius: 8px;
      background:
        linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        radial-gradient(circle at 20% 50%, rgba(35, 139, 113, 0.16), transparent 28%),
        #151819;
      background-size: 28px 28px, 28px 28px, auto, auto;
      overflow: hidden;
    }
    .map-graph {
      position: absolute;
      inset: 0;
      z-index: 1;
      transform-origin: 12% 50%;
      transition: transform 180ms ease;
    }
    .connectors {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
    }
    .connectors path {
      fill: none;
      stroke: rgba(152, 166, 160, 0.55);
      stroke-width: 2;
      stroke-linecap: round;
      filter: drop-shadow(0 0 8px rgba(36, 160, 127, 0.18));
    }
    .connectors path.is-selected {
      stroke: rgba(82, 210, 169, 0.95);
      stroke-width: 3;
    }
    .node {
      position: absolute;
      min-width: 0;
      width: clamp(168px, 20vw, 255px);
      border: 1px solid rgba(213, 227, 220, 0.18);
      border-radius: 8px;
      background: rgba(31, 38, 43, 0.94);
      padding: 13px;
      box-shadow: 0 16px 34px rgba(0, 0, 0, 0.28);
      overflow-wrap: anywhere;
      transform: translate(var(--x), var(--y));
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
      cursor: pointer;
    }
    .node:hover,
    .node.is-selected {
      border-color: rgba(82, 210, 169, 0.82);
      box-shadow: 0 18px 40px rgba(36, 160, 127, 0.2);
    }
    .node h3 {
      margin: 0 0 8px;
      font-size: 0.9rem;
      letter-spacing: 0;
    }
    .node p {
      margin: 0;
      color: #c9d6d0;
      font-size: 0.9rem;
      line-height: 1.4;
    }
    .node ul {
      margin: 8px 0 0;
      padding-left: 18px;
      color: #b9c8c1;
      font-size: 0.84rem;
      line-height: 1.36;
    }
    .node li + li { margin-top: 5px; }
    .center-node {
      left: 7%;
      top: 50%;
      width: clamp(190px, 19vw, 255px);
      background: linear-gradient(135deg, #11483f, #1b6072);
      border-color: rgba(127, 223, 192, 0.36);
      color: #ffffff;
      cursor: default;
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
    .branch-node {
      left: 44%;
      top: var(--top);
      border-left: 4px solid var(--accent);
    }
    .branch-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 7px;
    }
    .branch-toggle {
      display: inline-grid;
      place-items: center;
      width: 24px;
      height: 24px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      color: #e7f0ec;
      font-weight: 800;
      flex: 0 0 auto;
    }
    .leaf-node {
      left: 76%;
      top: var(--top);
      width: clamp(150px, 17vw, 220px);
      background: rgba(22, 27, 31, 0.94);
      border-color: rgba(199, 213, 207, 0.16);
      font-size: 0.84rem;
      cursor: default;
    }
    .leaf-node::before {
      content: "";
      position: absolute;
      left: -8px;
      top: 50%;
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--accent);
      transform: translateY(-50%);
    }
    .leaf-node p {
      font-size: 0.82rem;
    }
    .inspector {
      position: absolute;
      left: 18px;
      bottom: 18px;
      z-index: 3;
      width: min(420px, calc(100% - 36px));
      border: 1px solid rgba(217, 228, 222, 0.16);
      background: rgba(13, 17, 19, 0.86);
      border-radius: 8px;
      padding: 13px;
      box-shadow: 0 18px 36px rgba(0, 0, 0, 0.32);
      backdrop-filter: blur(10px);
    }
    .inspector h3 {
      margin: 0 0 8px;
      font-size: 0.95rem;
    }
    .inspector p,
    .inspector li {
      color: #c4d1cb;
      font-size: 0.84rem;
      line-height: 1.38;
    }
    .inspector ul {
      margin: 8px 0 0;
      padding-left: 18px;
    }
    details {
      margin-top: 14px;
      border: 1px solid rgba(217, 228, 222, 0.14);
      border-radius: 8px;
      background: rgba(15, 19, 22, 0.82);
      padding: 12px;
    }
    summary {
      cursor: pointer;
      font-weight: 700;
      color: #e5eee9;
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
      border-top: 1px solid rgba(232, 240, 236, 0.1);
      font-size: 0.9rem;
    }
    .muted { color: #98aaa2; font-size: 0.82rem; }
    @media (max-width: 820px) {
      header { align-items: start; flex-direction: column; }
      .status { justify-content: flex-start; }
      .grid { grid-template-columns: 1fr; }
      .map-shell { min-height: 910px; }
      .map-graph {
        transform: none !important;
      }
      .center-node,
      .branch-node,
      .leaf-node {
        left: 18px;
        top: var(--mobile-top, 18px);
        width: calc(100% - 36px);
      }
      .leaf-node { display: none; }
      .connectors { opacity: 0.28; }
      .inspector { display: none; }
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
        <div class="loop-panel">
          <h3>Agentic Loop</h3>
          <p id="loopPrompt">Waiting for the first startup map.</p>
          <div class="idea-options" id="ideaOptions"></div>
          <div class="loop-actions" id="loopActions"></div>
        </div>
      </section>

      <section>
        <div class="output-head">
          <h2>Live Output</h2>
          <div class="map-toolbar">
            <button id="zoomOut" type="button" aria-label="Zoom out">-</button>
            <button id="resetMap" type="button" aria-label="Reset map">1:1</button>
            <button id="zoomIn" type="button" aria-label="Zoom in">+</button>
          </div>
        </div>
        <div class="map-shell">
          <svg class="connectors" id="connectors"></svg>
          <div class="map-graph" id="map"></div>
          <aside class="inspector" id="inspector"></aside>
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
    const loopPromptEl = document.getElementById("loopPrompt");
    const loopActionsEl = document.getElementById("loopActions");
    const ideaOptionsEl = document.getElementById("ideaOptions");
    const mapEl = document.getElementById("map");
    const connectorsEl = document.getElementById("connectors");
    const inspectorEl = document.getElementById("inspector");
    const outputEl = document.getElementById("output");
    const runEl = document.getElementById("run");
    const queryEl = document.getElementById("query");
    const zoomOutEl = document.getElementById("zoomOut");
    const zoomInEl = document.getElementById("zoomIn");
    const resetMapEl = document.getElementById("resetMap");
    let currentMap = null;
    let selectedBranch = "profit";
    let mapScale = 1;
    let loopPrompts = {};
    let loopHistory = [];
    let actionCounts = {};
    const collapsedBranches = {};

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

    function shorten(value, maxLength = 120) {
      const text = String(value || "").replace(/\\s+/g, " ").trim();
      return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
    }

    function uniqueValues(values) {
      const seen = new Set();
      const result = [];
      for (const value of values) {
        const normalized = String(value || "").trim();
        const key = normalized.toLowerCase();
        if (normalized && !seen.has(key)) {
          seen.add(key);
          result.push(normalized);
        }
      }
      return result;
    }

    function escapeHTML(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function buildMindMap(report) {
      const idea = report.top_opportunity || {};
      const ideaOptions = uniqueValues([
        idea.name,
        ...(report.market_gaps || []).map((item) => item.gap),
        ...(report.trends || []).map((item) => item.trend),
      ]).slice(0, 5);
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

      return {
        idea: idea.name || "No opportunity selected yet",
        score: Number(report.opportunity_score || idea.score || 0),
        subtitle: `${report.market_saturation || "Unknown"} saturation / ${report.execution_difficulty || "Unknown"} execution`,
        ideaOptions,
        branches: [
          {
            id: "profit",
            title: "Profit",
            accent: "#39c78f",
            top: 15,
            mobileTop: 185,
            summary: `${report.monetization_potential || "Unknown"} monetization potential`,
            items: profitSignals,
          },
          {
            id: "people",
            title: "People",
            accent: "#70a6ff",
            top: 30,
            mobileTop: 330,
            summary: "Primary users and buyers",
            items: people,
          },
          {
            id: "target",
            title: "Target",
            accent: "#b184ff",
            top: 45,
            mobileTop: 475,
            summary: "Market wedge and timing",
            items: targets,
          },
          {
            id: "disadvantages",
            title: "Disadvantages",
            accent: "#ff6f72",
            top: 60,
            mobileTop: 620,
            summary: "Risks that weaken the opportunity",
            items: disadvantages,
          },
          {
            id: "loss",
            title: "Loss",
            accent: "#ffb45f",
            top: 75,
            mobileTop: 765,
            summary: "Downside signals",
            items: losses,
          },
        ],
      };
    }

    function renderBranchMap(report) {
      currentMap = buildMindMap(report);
      selectedBranch = currentMap.branches[0]?.id || "profit";
      renderMindMap();
    }

    function renderMindMap() {
      if (!currentMap) return;
      const branchHTML = currentMap.branches.map((branch) => {
        const isSelected = branch.id === selectedBranch;
        const isCollapsed = Boolean(collapsedBranches[branch.id]);
        return `
          <article
            class="node branch-node ${isSelected ? "is-selected" : ""}"
            data-node="branch"
            data-branch="${escapeHTML(branch.id)}"
            style="--top:${branch.top}%; --mobile-top:${branch.mobileTop}px; --x:0; --y:-50%; --accent:${branch.accent};"
          >
            <div class="branch-title">
              <h3>${escapeHTML(branch.title)}</h3>
              <span class="branch-toggle" data-toggle="${escapeHTML(branch.id)}">${isCollapsed ? "+" : "-"}</span>
            </div>
            <p>${escapeHTML(branch.summary)}</p>
          </article>
        `;
      }).join("");

      const selected = currentMap.branches.find((branch) => branch.id === selectedBranch) || currentMap.branches[0];
      const leafBaseTop = selected?.top || 45;
      const leafItems = collapsedBranches[selected?.id] ? [] : (selected?.items || []).slice(0, 4);
      const leafHTML = leafItems.map((item, index) => {
        const offset = (index - (leafItems.length - 1) / 2) * 10;
        const mobileTop = 910 + index * 92;
        return `
          <article
            class="node leaf-node"
            data-node="leaf"
            data-leaf-for="${escapeHTML(selected.id)}"
            style="--top:${leafBaseTop + offset}%; --mobile-top:${mobileTop}px; --x:0; --y:-50%; --accent:${selected.accent};"
          >
            <p>${escapeHTML(item)}</p>
          </article>
        `;
      }).join("");

      mapEl.innerHTML = `
        <article class="node center-node" data-node="center" style="--x:0; --y:-50%; --mobile-top:18px;">
          <h3>Startup Idea</h3>
          <p>${escapeHTML(currentMap.idea)}</p>
          <span class="score">score ${currentMap.score.toFixed(2)} / 10</span>
          <span class="score">${escapeHTML(currentMap.subtitle)}</span>
        </article>
        ${branchHTML}
        ${leafHTML}
      `;
      mapEl.style.transform = `scale(${mapScale})`;
      renderInspector();
      renderAgenticLoop();
      requestAnimationFrame(drawConnectors);
    }

    function renderEmptyMap(message) {
      currentMap = null;
      mapEl.innerHTML = `
        <article class="node center-node" data-node="center" style="--x:0; --y:-50%; --mobile-top:18px;">
          <h3>Startup Idea</h3>
          <p>${escapeHTML(message)}</p>
          <span class="score">waiting</span>
        </article>
      `;
      connectorsEl.innerHTML = "";
      inspectorEl.innerHTML = `
        <h3>Swarm Map</h3>
        <p>Run a report to generate the strategy branches.</p>
      `;
      loopPromptEl.textContent = "Waiting for the first startup map.";
      loopActionsEl.innerHTML = "";
      ideaOptionsEl.innerHTML = "";
    }

    function renderInspector() {
      if (!currentMap) return;
      const branch = currentMap.branches.find((item) => item.id === selectedBranch) || currentMap.branches[0];
      if (!branch) return;
      inspectorEl.innerHTML = `
        <h3>${escapeHTML(branch.title)}</h3>
        <p>${escapeHTML(branch.summary)}</p>
        ${listHTML(branch.items.slice(0, 4))}
      `;
    }

    function renderAgenticLoop() {
      if (!currentMap) return;
      loopPromptEl.textContent = loopHistory.length
        ? "Continue from the latest map. Repeated clicks go deeper instead of restarting."
        : "Choose the next addition or explore a different idea.";
      loopPrompts = {};

      ideaOptionsEl.innerHTML = currentMap.ideaOptions.slice(0, 4).map((idea, index) => {
        const id = `idea-${index}`;
        const actionKey = `idea:${idea.toLowerCase()}`;
        loopPrompts[id] = {
          actionKey,
          label: idea,
          prompt: makeRelativePrompt({
            actionKey,
            label: `Explore idea: ${idea}`,
            instruction: `Switch to this candidate startup idea: ${idea}. Build a fresh map, but use the latest map as context for what to preserve, reject, and compare.`,
          }),
        };
        return `<button type="button" data-loop-id="${id}">${escapeHTML(idea)}</button>`;
      }).join("");

      const actions = [
        {
          key: "another-idea",
          label: "Find another idea",
          instruction: "Find a different startup opportunity than the latest one. Keep the market context, but propose a stronger adjacent idea with profit, people, target, disadvantages, and loss.",
        },
        {
          key: "deepen-profit",
          label: "Deepen profit",
          instruction: "Deepen the latest profit branch. Add new revenue mechanics, pricing tests, buyer urgency, margin structure, and monetization risk.",
        },
        {
          key: "change-target",
          label: "Change target",
          instruction: "Change the target branch relative to the latest map. Compare who pays, who uses it, and who feels the pain most strongly.",
        },
        {
          key: "reduce-loss",
          label: "Reduce loss",
          instruction: "Reduce the latest loss and disadvantage branches. Redesign the idea to lower regulatory risk, adoption risk, operational loss, and technical fragility.",
        },
        {
          key: "add-moat",
          label: "Add moat",
          instruction: "Add defensibility relative to the latest map. Include data advantage, distribution, partnerships, workflow lock-in, and switching costs.",
        },
        {
          key: "find-mvp",
          label: "Find MVP",
          instruction: "Turn the latest idea into a 30-day MVP plan. Include first customer, simplest workflow, success metric, and launch wedge.",
        },
      ];

      loopActionsEl.innerHTML = actions.map((action, index) => {
        const id = `action-${index}`;
        const nextCount = (actionCounts[action.key] || 0) + 1;
        loopPrompts[id] = {
          actionKey: action.key,
          label: action.label,
          prompt: makeRelativePrompt({
            actionKey: action.key,
            label: action.label,
            instruction: action.instruction,
          }),
        };
        const label = nextCount > 1 ? `${action.label} ${nextCount}` : action.label;
        return `<button type="button" data-loop-id="${id}">${escapeHTML(label)}</button>`;
      }).join("");
    }

    function compactItems(values, maxItems = 3) {
      return (values || []).slice(0, maxItems).map((value) => shorten(value)).join("; ");
    }

    function currentBranchText(branchId) {
      if (!currentMap) return "";
      const branch = currentMap.branches.find((item) => item.id === branchId) || currentMap.branches[0];
      if (!branch) return "";
      return `${branch.title}: ${branch.summary}. Current points: ${compactItems(branch.items, 4)}`;
    }

    function mapSnapshot() {
      if (!currentMap) return queryEl.value;
      const branchLines = currentMap.branches
        .map((branch) => `${branch.title}: ${branch.summary}; ${compactItems(branch.items, 2)}`)
        .join(" | ");
      return `Latest idea: ${currentMap.idea}. Score: ${currentMap.score.toFixed(2)}. ${currentMap.subtitle}. Branches: ${branchLines}`;
    }

    function resetLoopMemory() {
      loopHistory = [];
      actionCounts = {};
      loopPrompts = {};
      for (const key of Object.keys(collapsedBranches)) {
        delete collapsedBranches[key];
      }
    }

    function historySnapshot() {
      if (!loopHistory.length) return "No previous loop steps.";
      return loopHistory
        .slice(-3)
        .map((step, index) => `${index + 1}. ${step.label} on ${step.idea}`)
        .join(" ");
    }

    function makeRelativePrompt({actionKey, label, instruction}) {
      const iteration = (actionCounts[actionKey] || 0) + 1;
      const selectedText = currentBranchText(selectedBranch);
      return [
        instruction,
        `Iteration ${iteration} for this action.`,
        `Use the latest map as source of truth, not the original first query.`,
        mapSnapshot(),
        selectedText ? `Currently selected branch: ${selectedText}` : "",
        `Recent loop history: ${historySnapshot()}`,
        `Do not repeat prior points. Add more specific, next-level analysis and return a refreshed startup map.`,
      ].filter(Boolean).join(" ");
    }

    function centerPoint(rect, shellRect, side) {
      const x = side === "right" ? rect.right : side === "left" ? rect.left : rect.left + rect.width / 2;
      return {
        x: x - shellRect.left,
        y: rect.top + rect.height / 2 - shellRect.top,
      };
    }

    function drawPath(start, end, className = "") {
      const curve = Math.max(80, Math.abs(end.x - start.x) * 0.52);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M ${start.x} ${start.y} C ${start.x + curve} ${start.y}, ${end.x - curve} ${end.y}, ${end.x} ${end.y}`);
      if (className) path.setAttribute("class", className);
      connectorsEl.append(path);
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
      const start = centerPoint(centerRect, shellRect, "right");
      connectorsEl.innerHTML = "";
      for (const branch of branches) {
        const rect = branch.getBoundingClientRect();
        const end = centerPoint(rect, shellRect, "left");
        drawPath(start, end, branch.dataset.branch === selectedBranch ? "is-selected" : "");
      }

      const selectedNode = mapEl.querySelector(`[data-branch="${selectedBranch}"]`);
      const leaves = mapEl.querySelectorAll(`[data-leaf-for="${selectedBranch}"]`);
      if (selectedNode && leaves.length) {
        const branchStart = centerPoint(selectedNode.getBoundingClientRect(), shellRect, "right");
        for (const leaf of leaves) {
          if (leaf.offsetParent === null) continue;
          const leafEnd = centerPoint(leaf.getBoundingClientRect(), shellRect, "left");
          drawPath(branchStart, leafEnd, "is-selected");
        }
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
        left.innerHTML = `<strong>${agent.fqan || agent.name}</strong><div class="muted">${(agent.capabilities || []).join(", ") || agent.category || "agent"}</div>`;
        const right = document.createElement("div");
        right.className = "muted";
        right.textContent = agent.status;
        row.append(left, right);
        agentsEl.append(row);
      }
    }

    async function runReport(options = {}) {
      const preserveLoop = Boolean(options && options.preserveLoop);
      if (!preserveLoop) {
        resetLoopMemory();
      }
      runEl.disabled = true;
      loopActionsEl.querySelectorAll("button").forEach((button) => {
        button.disabled = true;
      });
      ideaOptionsEl.querySelectorAll("button").forEach((button) => {
        button.disabled = true;
      });
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

    mapEl.addEventListener("click", (event) => {
      const branchEl = event.target.closest("[data-branch]");
      if (!branchEl || !currentMap) return;
      selectedBranch = branchEl.dataset.branch;
      if (event.target.closest("[data-toggle]")) {
        collapsedBranches[selectedBranch] = !collapsedBranches[selectedBranch];
      }
      renderMindMap();
    });

    function continueLoop(loopId) {
      const entry = loopPrompts[loopId];
      if (!entry) return;
      actionCounts[entry.actionKey] = (actionCounts[entry.actionKey] || 0) + 1;
      loopHistory.push({
        label: entry.label,
        idea: currentMap?.idea || "unknown idea",
        selectedBranch,
        prompt: entry.prompt,
      });
      loopHistory = loopHistory.slice(-8);
      queryEl.value = entry.prompt;
      runReport({preserveLoop: true});
    }

    loopActionsEl.addEventListener("click", (event) => {
      const button = event.target.closest("[data-loop-id]");
      if (!button) return;
      continueLoop(button.dataset.loopId);
    });

    ideaOptionsEl.addEventListener("click", (event) => {
      const button = event.target.closest("[data-loop-id]");
      if (!button) return;
      continueLoop(button.dataset.loopId);
    });

    zoomOutEl.addEventListener("click", () => {
      mapScale = Math.max(0.78, Number((mapScale - 0.08).toFixed(2)));
      renderMindMap();
    });

    zoomInEl.addEventListener("click", () => {
      mapScale = Math.min(1.2, Number((mapScale + 0.08).toFixed(2)));
      renderMindMap();
    });

    resetMapEl.addEventListener("click", () => {
      mapScale = 1;
      renderMindMap();
    });

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
