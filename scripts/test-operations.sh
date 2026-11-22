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
cat > "$CORE_TEST_OUTPUT/extra.json" <<'JSON'
{"services":{"backend":{"volumes":["calendars:/radicale-data","commercial:/commercial"],"environment":{"CANARY_COMMERCIAL_SERVICE_ENABLED":"0"}}},"volumes":{"calendars":{},"commercial":{}}}
JSON
compose=(docker compose --env-file /dev/null -p "$project" -f docker-compose.core-test.yml -f "$CORE_TEST_OUTPUT/extra.json")
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
"${compose[@]}" exec -T backend python -c "from pathlib import Path; Path('/radicale-data/synthetic.ics').write_text('BEGIN:VCALENDAR\\nVERSION:2.0\\nEND:VCALENDAR\\n'); Path('/commercial/synthetic-package.txt').write_text('Synthetic optional package; no provider code')"
python3 scripts/verify_operations.py "$CORE_TEST_OUTPUT"
