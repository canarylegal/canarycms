#!/usr/bin/env bash
# Phase 7b: previous Canary release tag → current checkout with firm package attached.
#
# Usage (repo root):
#   export FIRM_PACKAGE_DIR=/path/to/example-firm-pilot
#   PREV_TAG=v2.0.0 ./scripts/smoke-firm-dual-tag-upgrade.sh
#
# Optional:
#   PREV_TAG          git tag to start from (required)
#   COMPOSE_FILE      default docker-compose.yml:docker-compose.firm.example.yml
#   SKIP_SMOKE=1      stop after migrate/upgrade (no contract smoke)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PREV_TAG="${PREV_TAG:-}"
if [[ -z "$PREV_TAG" ]]; then
  echo "Set PREV_TAG to a prior Canary release tag (e.g. v2.0.0)" >&2
  exit 2
fi
if [[ -z "${FIRM_PACKAGE_DIR:-}" ]]; then
  echo "Set FIRM_PACKAGE_DIR to the firm package path" >&2
  exit 2
fi

export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml:docker-compose.firm.example.yml}"
CURRENT_REF="$(git rev-parse HEAD)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

cleanup() {
  # Best-effort return to starting ref
  git checkout -q "$CURRENT_REF" 2>/dev/null || git checkout -q "$CURRENT_BRANCH" 2>/dev/null || true
}
trap cleanup EXIT

echo "== Dual-tag upgrade: ${PREV_TAG} → ${CURRENT_REF} (firm=${FIRM_PACKAGE_DIR}) =="

git fetch --tags --quiet || true
git checkout -q "$PREV_TAG"

echo "-- Start stack on previous tag --"
GIT_COMMIT="$(git rev-parse HEAD)" \
  docker compose --profile prod up -d --build db backend
./scripts/smoke-firm-contract.sh --ensure-fixture || true

echo "-- Checkout current and upgrade in place --"
git checkout -q "$CURRENT_REF"
GIT_COMMIT="$(git rev-parse HEAD)" \
  docker compose --profile prod up -d --build --force-recreate backend

if [[ "${SKIP_SMOKE:-0}" == "1" ]]; then
  echo "SKIP_SMOKE=1 — upgrade recreate done; not running contract smoke"
  exit 0
fi

./scripts/smoke-firm-contract.sh --ensure-fixture
echo "Dual-tag upgrade contract smoke passed (${PREV_TAG} → HEAD)."
