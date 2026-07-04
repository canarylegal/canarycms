#!/bin/bash
# Deploy e-mail compose subject fix to Canary backend.
# Run on the server as root after copying files into /opt/canarycms.
set -euo pipefail

CANARY_ROOT="${CANARY_ROOT:-/opt/canarycms}"
FILES_SRC="${FILES_SRC:-$CANARY_ROOT/backend/app/routers/files.py}"
TEST_SRC="${TEST_SRC:-$CANARY_ROOT/backend/tests/test_case_email_compose_subject.py}"

if [ ! -f "$FILES_SRC" ]; then
  echo "ERROR: $FILES_SRC not found"
  exit 1
fi

echo "=== Rebuild backend (compose subject fix) ==="
cd "$CANARY_ROOT"
docker compose --profile prod build backend
docker compose --profile prod up -d backend

echo ""
echo "=== Quick test (optional) ==="
if [ -f "$TEST_SRC" ]; then
  docker compose --profile prod exec -T backend pytest backend/tests/test_case_email_compose_subject.py -q || true
fi

echo "Done. New > E-mail handoffs will use matter description (case title) as subject."
