#!/usr/bin/env bash
# Synthetic data and capped resources in a new internal-only Docker project.
set -euo pipefail
cd "$(dirname "$0")/.."
export CORE_TEST_OUTPUT="${CORE_TEST_OUTPUT:-$(pwd)/artifacts/performance}"
mkdir -p "$CORE_TEST_OUTPUT"
CORE_TEST_OUTPUT=$(realpath "$CORE_TEST_OUTPUT")
export CORE_TEST_OUTPUT
project="canaryperf-$(date +%s)-$$"
compose=(docker compose --env-file /dev/null -p "$project" -f docker-compose.core-test.yml -f docker-compose.performance.yml)
stats_pid=''
cleanup() {
  status=$?
  trap - EXIT
  if [[ -n "$stats_pid" ]]; then
    kill "$stats_pid" 2>/dev/null || true
    wait "$stats_pid" 2>/dev/null || true
    python3 scripts/summarize_performance_resources.py "$CORE_TEST_OUTPUT" || status=1
  fi
  "${compose[@]}" logs --no-color > "$CORE_TEST_OUTPUT/services.log" 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans > "$CORE_TEST_OUTPUT/cleanup.log" 2>&1 || status=1
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" --profile test build > "$CORE_TEST_OUTPUT/build.log" 2>&1
"${compose[@]}" up -d --wait --wait-timeout 600 db backend onlyoffice frontend
"${compose[@]}" exec -T backend python scripts/ensure_core_workflow_fixture.py
"${compose[@]}" exec -T backend python scripts/seed_performance_fixture.py
"${compose[@]}" run --rm --no-deps -T -v "$(pwd)/backend/tests:/app/tests:ro" \
  -e DATABASE_URL=postgresql+psycopg://canary:isolated-core-database-secret@db:5432/canary_core_test \
  backend pytest -q tests/test_matter_menu.py tests/test_document_pages.py
"${compose[@]}" exec -T backend python scripts/profile_performance.py --assert-budgets > "$CORE_TEST_OUTPUT/api-metrics.json"
"${compose[@]}" exec -T backend python scripts/profile_large_documents.py --cold-statistics --assert-budgets > "$CORE_TEST_OUTPUT/large-api-cold.json"
"${compose[@]}" exec -T backend python scripts/profile_large_documents.py --analyze --assert-budgets > "$CORE_TEST_OUTPUT/large-api-metrics.json"
mapfile -t containers < <("${compose[@]}" ps -q)
docker stats --format '{{json .}}' "${containers[@]}" > "$CORE_TEST_OUTPUT/resource-samples.raw" &
stats_pid=$!
"${compose[@]}" --profile test run --rm --no-deps --user "$(id -u):$(id -g)" -e HOME=/tmp -e CANARY_SOAK_SECONDS="${CANARY_SOAK_SECONDS:-300}" tests npx playwright test -c playwright.performance.config.ts
# Assert the load did not restart or OOM any infrastructure container.
for container in "${containers[@]}"; do
  state=$(docker inspect --format '{{.RestartCount}} {{.State.OOMKilled}} {{.State.Running}}' "$container")
  [[ "$state" == "0 false true" ]] || { echo "Unexpected container state: $state" >&2; exit 1; }
done
