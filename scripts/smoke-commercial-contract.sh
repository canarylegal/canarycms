#!/usr/bin/env bash
# Core-side commercial attach/detach contract (no full Compose required).
#
# Usage:
#   export COMMERCIAL_PACKAGE_DIR=/path/to/canary-commercial
#   ./scripts/smoke-commercial-contract.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CANARY_DIR="${CANARY_DIR:-$ROOT}"
BACKEND="$CANARY_DIR/backend"
COMMERCIAL_PACKAGE_DIR="${COMMERCIAL_PACKAGE_DIR:?Set COMMERCIAL_PACKAGE_DIR to canary-commercial checkout}"

if [[ ! -f "$COMMERCIAL_PACKAGE_DIR/canary-commercial.json" ]]; then
  echo "error: $COMMERCIAL_PACKAGE_DIR has no canary-commercial.json" >&2
  exit 1
fi

PY="${BACKEND}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${PYTHON:-python3}"
fi

export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///:memory:}"
export JWT_SECRET="${JWT_SECRET:-test-jwt-secret-for-pytest-only}"
export DATA_ENCRYPTION_KEY="${DATA_ENCRYPTION_KEY:-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=}"
export FILES_ROOT="${FILES_ROOT:-/tmp/canary-commercial-contract-files}"
export MASTER_ADMIN_LOGIN="${MASTER_ADMIN_LOGIN:-ci-master-pytest-admin}"
export MASTER_ADMIN_PASSWORD="${MASTER_ADMIN_PASSWORD:-ci-master-pytest-password}"
export MASTER_ADMIN_REQUIRE_2FA=false
export CANARY_PRODUCT_VERSION="${CANARY_PRODUCT_VERSION:-2.0.0}"
mkdir -p "$FILES_ROOT"

cd "$BACKEND"

echo "== Core alone =="
env -u COMMERCIAL_PACKAGE_DIR "$PY" - <<'PY'
import os, sys
sys.path.insert(0, ".")
os.environ.pop("COMMERCIAL_PACKAGE_DIR", None)
from app.commercial_package import evaluate_commercial_package_status
from app.main import app
st = evaluate_commercial_package_status(force=True)
assert not st.attached and not st.loaded, st.as_dict()
paths = [getattr(r, "path", "") or "" for r in app.routes]
assert not any("docusign" in p for p in paths)
assert any(p.startswith("/commercial-package") for p in paths)
print("pass alone:", st.as_dict())
PY

echo "== Core + commercial =="
COMMERCIAL_PACKAGE_DIR="$COMMERCIAL_PACKAGE_DIR" "$PY" - <<PY
import os, sys
sys.path.insert(0, ".")
os.environ["COMMERCIAL_PACKAGE_DIR"] = r"""$COMMERCIAL_PACKAGE_DIR"""
from app.commercial_package import evaluate_commercial_package_status
from app.main import app
st = evaluate_commercial_package_status(force=True)
assert st.attached and st.compatible and st.loaded, st.as_dict()
paths = [getattr(r, "path", "") or "" for r in app.routes]
assert any("docusign" in p for p in paths)
assert any("casera" in p for p in paths)
assert any("hmlr" in p or "land-registry" in p for p in paths)
print("pass attached:", st.as_dict())
PY

echo "smoke-commercial-contract: OK"
