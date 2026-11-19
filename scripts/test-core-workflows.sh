#!/usr/bin/env bash
# Creates and removes ONLY its uniquely named disposable stack.
set -euo pipefail
cd "$(dirname "$0")/.."
export CORE_TEST_OUTPUT="${CORE_TEST_OUTPUT:-$(pwd)/artifacts/core-workflows}"
mkdir -p "$CORE_TEST_OUTPUT"
CORE_TEST_OUTPUT=$(realpath "$CORE_TEST_OUTPUT")
export CORE_TEST_OUTPUT
project="canarycore-$(date +%s)-$$"
compose=(docker compose --env-file /dev/null -p "$project" -f docker-compose.core-test.yml)
cleanup() {
  status=$?
  trap - EXIT
  "${compose[@]}" logs --no-color > "$CORE_TEST_OUTPUT/services.log" 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans > "$CORE_TEST_OUTPUT/cleanup.log" 2>&1 || true
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" --profile test build > "$CORE_TEST_OUTPUT/build.log" 2>&1
"${compose[@]}" up -d --wait --wait-timeout 600 db backend onlyoffice frontend
"${compose[@]}" exec -T backend python scripts/ensure_core_workflow_fixture.py
"${compose[@]}" --profile test run --rm --no-deps --user "$(id -u):$(id -g)" -e HOME=/tmp tests
