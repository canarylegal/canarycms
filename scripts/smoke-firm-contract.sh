#!/usr/bin/env bash
# Phase 7 MVP: firm-platform contract smoke (compat / migrate / API / lifecycle).
#
# Requires a running backend with a firm package attached (e.g. example-firm-pilot).
#
# Usage (from repo root):
#   ./scripts/smoke-firm-contract.sh
#   ./scripts/smoke-firm-contract.sh --ensure-fixture
#   make smoke-firm-contract
#   make smoke-firm-contract-ci
#
# Prefers container canary-backend; override with BACKEND_CONTAINER=… or compose.
# CI uses BACKEND_CONTAINER=canaryci-backend (see docker-compose.ci.yml).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENSURE_FIXTURE=0
BACKEND_CONTAINER="${BACKEND_CONTAINER:-canary-backend}"
COMPOSE_DIR="${CANARY_COMPOSE_DIR:-$ROOT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ensure-fixture)
      ENSURE_FIXTURE=1
      ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

USE_COMPOSE=0
if docker inspect -f '{{.State.Running}}' "$BACKEND_CONTAINER" 2>/dev/null | grep -qx true; then
  echo "Using container ${BACKEND_CONTAINER}"
elif (cd "$COMPOSE_DIR" && docker compose exec -T backend true >/dev/null 2>&1); then
  USE_COMPOSE=1
  echo "Using docker compose backend in ${COMPOSE_DIR}"
else
  echo "No running backend found (tried container '${BACKEND_CONTAINER}' and compose in ${COMPOSE_DIR})." >&2
  echo "Attach a firm package and start the stack, e.g.:" >&2
  echo "  export FIRM_PACKAGE_DIR=../example-firm-pilot" >&2
  echo "  docker compose -f docker-compose.yml -f docker-compose.firm.example.yml --profile prod up -d" >&2
  exit 1
fi

run_backend() {
  if [[ "$USE_COMPOSE" -eq 1 ]]; then
    (cd "$COMPOSE_DIR" && docker compose exec -T \
      -e "FIRM_CONTRACT_BASE=http://127.0.0.1:8000" \
      -e "FIRM_CONTRACT_STAFF_EMAIL=${FIRM_CONTRACT_STAFF_EMAIL:-}" \
      backend "$@")
  else
    docker exec -i \
      -e "FIRM_CONTRACT_BASE=http://127.0.0.1:8000" \
      -e "FIRM_CONTRACT_STAFF_EMAIL=${FIRM_CONTRACT_STAFF_EMAIL:-}" \
      "$BACKEND_CONTAINER" "$@"
  fi
}

echo "Waiting for backend health…"
for _ in $(seq 1 60); do
  if run_backend python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" \
    >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! run_backend python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" \
  >/dev/null 2>&1; then
  echo "backend health check failed" >&2
  exit 1
fi

if [[ "$ENSURE_FIXTURE" -eq 1 ]]; then
  echo "Ensuring firm contract fixture (staff + Purchase matter)…"
  run_backend python scripts/ensure_firm_contract_fixture.py
fi

echo "Running firm contract smoke…"
run_backend python scripts/smoke_firm_contract.py
