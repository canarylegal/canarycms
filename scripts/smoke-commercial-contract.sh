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
from types import SimpleNamespace

sys.path.insert(0, ".")
os.environ.pop("COMMERCIAL_PACKAGE_DIR", None)

from fastapi.testclient import TestClient
from app.commercial_package import evaluate_commercial_package_status
from app.deps import get_current_user
from app.main import app

st = evaluate_commercial_package_status(force=True)
assert not st.attached and not st.loaded, st.as_dict()
paths = [getattr(r, "path", "") or "" for r in app.routes]
assert not any("docusign" in p for p in paths)
assert any(p.startswith("/commercial-package") for p in paths)
assert any("commercial-modules" in p for p in paths)

staff = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", role="admin", is_active=True)
app.dependency_overrides[get_current_user] = lambda: staff
client = TestClient(app)

active = client.get("/commercial-modules/active")
assert active.status_code == 200, active.text
body = active.json()
assert body.get("enabled") is False, body
assert body.get("ui") is None, body

ui = client.get("/commercial-modules/active/ui/commercial-module.js")
assert ui.status_code == 404, ui.text

print("pass alone:", st.as_dict())
print("pass alone http: commercial-modules disabled, UI 404")
PY

echo "== Core + commercial =="
COMMERCIAL_PACKAGE_DIR="$COMMERCIAL_PACKAGE_DIR" "$PY" - <<PY
import os, sys
from types import SimpleNamespace

sys.path.insert(0, ".")
os.environ["COMMERCIAL_PACKAGE_DIR"] = r"""$COMMERCIAL_PACKAGE_DIR"""

from fastapi.testclient import TestClient
from app.commercial_package import evaluate_commercial_package_status
from app.commercial_module_runtime import load_manifest
from app.deps import get_current_user
from app.main import app

st = evaluate_commercial_package_status(force=True)
assert st.attached and st.compatible and st.loaded, st.as_dict()
paths = [getattr(r, "path", "") or "" for r in app.routes]
assert any("docusign" in p for p in paths)
assert any("casera" in p for p in paths)
assert any("hmlr" in p or "land-registry" in p for p in paths)
assert any("commercial-modules" in p for p in paths)

m = load_manifest(force=True)
assert m and m.get("ui"), m

expected_slots = {
    "admin_integrations",
    "matter_searches",
    "matter_land_registry",
    "app_docusign",
    "modal_send_docusign",
}
expected_exports = {
    "admin_integrations": "AdminIntegrations",
    "matter_searches": "MatterSearchesPanel",
    "matter_land_registry": "MatterLandRegistryPanel",
    "app_docusign": "DocusignPage",
    "modal_send_docusign": "SendDocusignModal",
}

staff = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", role="admin", is_active=True)
app.dependency_overrides[get_current_user] = lambda: staff
client = TestClient(app)

active = client.get("/commercial-modules/active")
assert active.status_code == 200, active.text
body = active.json()
assert body.get("enabled") is True, body
assert body.get("module_id") == "canary_commercial", body
slots = body.get("slots") or {}
assert expected_slots <= set(slots), slots
assert all(slots[k] is True for k in expected_slots), slots
ui = body.get("ui") or {}
bundle_url = ui.get("bundle_url") or ""
assert bundle_url.startswith("/commercial-modules/active/ui/commercial-module.js"), ui
exports = ui.get("exports") or {}
for key, name in expected_exports.items():
    assert exports.get(key) == name, (key, exports)

bundle = client.get(bundle_url)
assert bundle.status_code == 200, bundle.text
assert "javascript" in (bundle.headers.get("content-type") or "").lower() or bundle.content[:20]
assert b"CanaryCommercialModule" in bundle.content, bundle.content[:120]
assert len(bundle.content) > 10_000, len(bundle.content)

print("pass attached:", st.as_dict())
print("pass module http:", {
    "module_id": body.get("module_id"),
    "slots": slots,
    "bundle_bytes": len(bundle.content),
    "exports": exports,
})
PY

echo "smoke-commercial-contract: OK"
