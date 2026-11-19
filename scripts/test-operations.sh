#!/usr/bin/env bash
# All services, volumes and failures belong to this new disposable test project.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export CORE_TEST_OUTPUT="${CORE_TEST_OUTPUT:-$(pwd)/artifacts/operations-private}"
mkdir -p "$CORE_TEST_OUTPUT"
CORE_TEST_OUTPUT=$(realpath "$CORE_TEST_OUTPUT")
export CORE_TEST_OUTPUT
project="canaryops-$(date +%s)-$$"
compose=(docker compose --env-file /dev/null -p "$project" -f docker-compose.core-test.yml)
cleanup() {
  status=$?
  trap - EXIT
  "${compose[@]}" down --volumes --remove-orphans > "$CORE_TEST_OUTPUT/cleanup.log" 2>&1 || status=1
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" build backend frontend > "$CORE_TEST_OUTPUT/build.log" 2>&1
"${compose[@]}" up -d --wait --wait-timeout 600 db backend onlyoffice frontend > "$CORE_TEST_OUTPUT/start.log" 2>&1
"${compose[@]}" exec -T backend python scripts/ensure_core_workflow_fixture.py
"${compose[@]}" exec -T backend python scripts/seed_operations_fixture.py
"${compose[@]}" config --format json > "$CORE_TEST_OUTPUT/compose.json"
python3 scripts/verify_operations.py "$CORE_TEST_OUTPUT"
