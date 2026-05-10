#!/usr/bin/env sh
set -eu

APP_PORT="${PORT:-7860}"

export PYTHONUNBUFFERED=1
export DIRECTORY_URL="${DIRECTORY_URL:-http://127.0.0.1:8000}"
export ZYND_REGISTRY_URL="${ZYND_REGISTRY_URL:-http://127.0.0.1:8000}"
export ZNS_ROOT="${ZNS_ROOT:-zns01.zynd.ai}"
export ZNS_DEVELOPER_HANDLE="${ZNS_DEVELOPER_HANDLE:-venture-swarm}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export ORCHESTRATOR_SDK_WEBHOOK_PORT="${ORCHESTRATOR_SDK_WEBHOOK_PORT:-9201}"

pids=""

start_service() {
  name="$1"
  shift
  echo "[Startup] ${name} starting"
  "$@" &
  pid="$!"
  pids="${pids} ${pid}"
  echo "[Startup] ${name} pid=${pid}"
}

shutdown() {
  echo "[Shutdown] Stopping VentureSwarm services"
  for pid in ${pids}; do
    kill "${pid}" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

trap shutdown INT TERM

start_service "directory" \
  uvicorn registry.app:app --host 0.0.0.0 --port 8000

sleep 2

start_service "trend-agent" \
  env SERVICE_URL=http://127.0.0.1:8101 \
  uvicorn agents.trend_agent.agent:app --host 127.0.0.1 --port 8101

start_service "funding-agent" \
  env SERVICE_URL=http://127.0.0.1:8102 PREMIUM_REQUIRED="${FUNDING_PREMIUM_REQUIRED:-false}" \
  uvicorn agents.funding_agent.agent:app --host 127.0.0.1 --port 8102

start_service "benchmarking-agent" \
  env SERVICE_URL=http://127.0.0.1:8106 PREMIUM_REQUIRED="${BENCHMARK_PREMIUM_REQUIRED:-false}" \
  uvicorn agents.benchmarking_agent.agent:app --host 127.0.0.1 --port 8106

start_service "competitor-agent" \
  env SERVICE_URL=http://127.0.0.1:8103 \
  uvicorn agents.competitor_agent.agent:app --host 127.0.0.1 --port 8103

start_service "startup-compare-agent" \
  env SERVICE_URL=http://127.0.0.1:8108 \
  uvicorn agents.startup_compare_agent.agent:app --host 127.0.0.1 --port 8108

start_service "market-gap-agent" \
  env SERVICE_URL=http://127.0.0.1:8104 \
  uvicorn agents.market_gap_agent.agent:app --host 127.0.0.1 --port 8104

start_service "financial-signals-agent" \
  env SERVICE_URL=http://127.0.0.1:8107 \
  uvicorn agents.financial_signals_agent.agent:app --host 127.0.0.1 --port 8107

start_service "risk-agent" \
  env SERVICE_URL=http://127.0.0.1:8105 \
  uvicorn agents.risk_agent.agent:app --host 127.0.0.1 --port 8105

sleep 2

start_service "orchestrator" \
  uvicorn main:app --host 0.0.0.0 --port "${APP_PORT}"

echo "[Startup] VentureSwarm Hugging Face Space ready on port ${APP_PORT}"

while :; do
  for pid in ${pids}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "[Shutdown] Service pid=${pid} exited"
      shutdown
      exit 1
    fi
  done
  sleep 2
done
