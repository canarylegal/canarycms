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
# Keep PostgreSQL integration fixtures out of the browser's progressive matter list.
"${compose[@]}" exec -T db createdb -U canary canary_integration_test
integration_url=postgresql+psycopg://canary:isolated-core-database-secret@db:5432/canary_integration_test
"${compose[@]}" exec -T -e DATABASE_URL="$integration_url" backend alembic upgrade head
"${compose[@]}" run --rm --no-deps -T -v "$(pwd)/backend/tests:/app/tests:ro" \
  -e DATABASE_URL="$integration_url" \
  backend pytest -q tests/test_upload_recovery_postgres.py tests/test_document_durability_postgres.py tests/test_invoice_allocation_postgres.py tests/test_bank_integrity_postgres.py tests/test_ledger_operations_postgres.py tests/test_invoice_corrections_postgres.py tests/test_financial_reports_postgres.py tests/test_financial_validation_postgres.py tests/test_historical_corrections_postgres.py tests/test_accounting_periods_postgres.py tests/test_financial_snapshots_postgres.py tests/test_document_filing_postgres.py tests/test_notification_outbox_postgres.py
"${compose[@]}" --profile test run --rm --no-deps --user "$(id -u):$(id -g)" -e HOME=/tmp tests

# The receipt must survive a real backend restart, not just a browser retry.
"${compose[@]}" exec -T backend python < backend/scripts/check_import_restart.py > "$CORE_TEST_OUTPUT/import-before-restart.json"
"${compose[@]}" exec -T backend python scripts/check_document_recovery_restart.py prepare
"${compose[@]}" exec -T backend python < backend/scripts/check_ledger_restart.py > "$CORE_TEST_OUTPUT/ledger-before-restart.json"
"${compose[@]}" exec -T backend python < backend/scripts/check_allocation_restart.py > "$CORE_TEST_OUTPUT/allocation-before-restart.json"
"${compose[@]}" exec -T backend python scripts/check_document_creation.py > "$CORE_TEST_OUTPUT/creation-before-restart.json"
"${compose[@]}" exec -T -e DATABASE_URL="$integration_url" backend python scripts/check_notification_outbox.py > "$CORE_TEST_OUTPUT/outbox-before-restart.json"
"${compose[@]}" restart backend
"${compose[@]}" up -d --wait --wait-timeout 120 backend
"${compose[@]}" exec -T backend python < backend/scripts/check_import_restart.py > "$CORE_TEST_OUTPUT/import-after-restart.json"
cmp "$CORE_TEST_OUTPUT/import-before-restart.json" "$CORE_TEST_OUTPUT/import-after-restart.json"
"${compose[@]}" exec -T backend python scripts/check_document_recovery_restart.py verify
"${compose[@]}" exec -T backend python scripts/check_document_creation.py > "$CORE_TEST_OUTPUT/creation-after-restart.json"
cmp "$CORE_TEST_OUTPUT/creation-before-restart.json" "$CORE_TEST_OUTPUT/creation-after-restart.json"

"${compose[@]}" exec -T backend python < backend/scripts/check_ledger_restart.py > "$CORE_TEST_OUTPUT/ledger-after-restart.json"
cmp "$CORE_TEST_OUTPUT/ledger-before-restart.json" "$CORE_TEST_OUTPUT/ledger-after-restart.json"

"${compose[@]}" exec -T backend python < backend/scripts/check_allocation_restart.py > "$CORE_TEST_OUTPUT/allocation-after-restart.json"
cmp "$CORE_TEST_OUTPUT/allocation-before-restart.json" "$CORE_TEST_OUTPUT/allocation-after-restart.json"

"${compose[@]}" exec -T backend python scripts/check_invoice_allocations.py > "$CORE_TEST_OUTPUT/allocation-consistency.json"

# Approval archives and their mutation guards must survive a real database restore.
"${compose[@]}" exec -T -e DATABASE_URL="$integration_url" backend python scripts/check_financial_snapshots.py > "$CORE_TEST_OUTPUT/snapshots-before-restore.json"
"${compose[@]}" exec -T db pg_dump -U canary -d canary_integration_test -Fc > "$CORE_TEST_OUTPUT/snapshots-restore.dump"
"${compose[@]}" exec -T db createdb -U canary canary_snapshot_restore
"${compose[@]}" exec -T db pg_restore -U canary -d canary_snapshot_restore --exit-on-error < "$CORE_TEST_OUTPUT/snapshots-restore.dump"
"${compose[@]}" exec -T -e DATABASE_URL=postgresql+psycopg://canary:isolated-core-database-secret@db:5432/canary_snapshot_restore backend python scripts/check_financial_snapshots.py > "$CORE_TEST_OUTPUT/snapshots-after-restore.json"
cmp "$CORE_TEST_OUTPUT/snapshots-before-restore.json" "$CORE_TEST_OUTPUT/snapshots-after-restore.json"
"${compose[@]}" exec -T -e DATABASE_URL="$integration_url" backend python scripts/check_notification_outbox.py > "$CORE_TEST_OUTPUT/outbox-after-restart.json"
cmp "$CORE_TEST_OUTPUT/outbox-before-restart.json" "$CORE_TEST_OUTPUT/outbox-after-restart.json"
"${compose[@]}" exec -T -e DATABASE_URL=postgresql+psycopg://canary:isolated-core-database-secret@db:5432/canary_snapshot_restore backend python scripts/check_notification_outbox.py > "$CORE_TEST_OUTPUT/outbox-after-restore.json"
cmp "$CORE_TEST_OUTPUT/outbox-before-restart.json" "$CORE_TEST_OUTPUT/outbox-after-restore.json"
# Restored triggers must still reject mutation (psql stops with a nonzero status).
if "${compose[@]}" exec -T db psql -U canary -d canary_snapshot_restore -v ON_ERROR_STOP=1 -c 'TRUNCATE financial_report_snapshot CASCADE' > "$CORE_TEST_OUTPUT/restored-mutation-guard.log" 2>&1; then
  echo 'Restored archive mutation guard failed' >&2
  exit 1
fi
grep -q 'Approved financial snapshots are immutable' "$CORE_TEST_OUTPUT/restored-mutation-guard.log"
"${compose[@]}" exec -T db dropdb -U canary canary_snapshot_restore
