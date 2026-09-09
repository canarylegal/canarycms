#!/usr/bin/env bash
# Run client-portal smoke tests (quote / form / Canary Sign) against the live stack.
#
# Usage (from repo root):
#   ./scripts/smoke-portal.sh
#   ./scripts/smoke-portal.sh --ensure-fixture
#   ./scripts/smoke-portal.sh --seed          # also run portal demo seed
#   ./scripts/smoke-portal.sh --reset-demo    # void leftover pending + re-seed
#   CASE_NUMBER=000002 ./scripts/smoke-portal.sh
#
# Prefers the running container named canary-backend (compose container_name).
# Override with BACKEND_CONTAINER=... or fall back to `docker compose exec backend`
# from COMPOSE_DIR (default: repo root, or CANARY_COMPOSE_DIR).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENSURE_FIXTURE=0
SEED_DEMO=0
RESET_DEMO=0
CASE_NUMBER="${CASE_NUMBER:-000002}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-canary-backend}"
COMPOSE_DIR="${CANARY_COMPOSE_DIR:-$ROOT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ensure-fixture)
      ENSURE_FIXTURE=1
      ;;
    --seed)
      SEED_DEMO=1
      ENSURE_FIXTURE=1
      ;;
    --reset-demo)
      RESET_DEMO=1
      ENSURE_FIXTURE=1
      ;;
    --case)
      shift
      CASE_NUMBER="${1:?--case requires a matter number}"
      ;;
    -h|--help)
      sed -n '2,15p' "$0"
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
  echo "Start the stack first, e.g. docker compose --profile prod up -d" >&2
  exit 1
fi

run_backend() {
  # Remaining args are the command inside the container (e.g. python scripts/...)
  if [[ "$USE_COMPOSE" -eq 1 ]]; then
    (cd "$COMPOSE_DIR" && docker compose exec -T \
      -e "CASE_NUMBER=${CASE_NUMBER}" \
      -e "PORTAL_SMOKE_BASE=http://127.0.0.1:8000" \
      -e "I_CONFIRM_CANARY_SEED=${I_CONFIRM_CANARY_SEED:-}" \
      backend "$@")
  else
    docker exec -i \
      -e "CASE_NUMBER=${CASE_NUMBER}" \
      -e "PORTAL_SMOKE_BASE=http://127.0.0.1:8000" \
      -e "I_CONFIRM_CANARY_SEED=${I_CONFIRM_CANARY_SEED:-}" \
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
  echo "Ensuring portal smoke fixture (matter ${CASE_NUMBER})…"
  run_backend python scripts/ensure_portal_smoke_fixture.py
fi

if [[ "$RESET_DEMO" -eq 1 ]]; then
  echo "Resetting portal demo (void pending + re-seed)…"
  I_CONFIRM_CANARY_SEED=yes run_backend python scripts/reset_portal_demo.py
elif [[ "$SEED_DEMO" -eq 1 ]]; then
  echo "Seeding portal demo content…"
  I_CONFIRM_CANARY_SEED=yes run_backend python scripts/seed_case_000002_portal_demo.py
fi

echo "Running portal smoke flows…"
run_backend python scripts/smoke_portal_flows.py
