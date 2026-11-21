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
"${compose[@]}" run --rm --no-deps -T -v "$(pwd)/backend/tests:/app/tests:ro" \
  -e DATABASE_URL=postgresql+psycopg://canary:isolated-core-database-secret@db:5432/canary_core_test \
  backend pytest -q tests/test_upload_recovery_postgres.py tests/test_document_durability_postgres.py tests/test_invoice_allocation_postgres.py tests/test_bank_integrity_postgres.py tests/test_ledger_operations_postgres.py tests/test_invoice_corrections_postgres.py tests/test_financial_reports_postgres.py tests/test_financial_validation_postgres.py tests/test_historical_corrections_postgres.py tests/test_accounting_periods_postgres.py
"${compose[@]}" --profile test run --rm --no-deps --user "$(id -u):$(id -g)" -e HOME=/tmp tests

# The receipt must survive a real backend restart, not just a browser retry.
"${compose[@]}" exec -T backend python < backend/scripts/check_import_restart.py > "$CORE_TEST_OUTPUT/import-before-restart.json"
"${compose[@]}" exec -T backend python scripts/check_document_recovery_restart.py prepare
"${compose[@]}" exec -T backend python < backend/scripts/check_ledger_restart.py > "$CORE_TEST_OUTPUT/ledger-before-restart.json"
"${compose[@]}" exec -T backend python < backend/scripts/check_allocation_restart.py > "$CORE_TEST_OUTPUT/allocation-before-restart.json"
"${compose[@]}" restart backend
"${compose[@]}" up -d --wait --wait-timeout 120 backend
"${compose[@]}" exec -T backend python < backend/scripts/check_import_restart.py > "$CORE_TEST_OUTPUT/import-after-restart.json"
cmp "$CORE_TEST_OUTPUT/import-before-restart.json" "$CORE_TEST_OUTPUT/import-after-restart.json"
"${compose[@]}" exec -T backend python scripts/check_document_recovery_restart.py verify

"${compose[@]}" exec -T backend python < backend/scripts/check_ledger_restart.py > "$CORE_TEST_OUTPUT/ledger-after-restart.json"
cmp "$CORE_TEST_OUTPUT/ledger-before-restart.json" "$CORE_TEST_OUTPUT/ledger-after-restart.json"

"${compose[@]}" exec -T backend python < backend/scripts/check_allocation_restart.py > "$CORE_TEST_OUTPUT/allocation-after-restart.json"
cmp "$CORE_TEST_OUTPUT/allocation-before-restart.json" "$CORE_TEST_OUTPUT/allocation-after-restart.json"

"${compose[@]}" exec -T backend python scripts/check_invoice_allocations.py > "$CORE_TEST_OUTPUT/allocation-consistency.json"
