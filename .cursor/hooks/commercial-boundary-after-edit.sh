#!/usr/bin/env bash
# After agent edits, remind if commercial vendor files landed in Core.
set -euo pipefail
input="$(cat)"
file_path="$(printf '%s' "$input" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("file_path") or d.get("path") or "")' 2>/dev/null || true)"

# Only run the full check when edits touch likely boundary surfaces.
case "$file_path" in
  *backend/alembic/versions/*|*backend/app/routers/*|*frontend/src/Admin*|*frontend/src/case/*|*frontend/src/*Casera*|*frontend/src/*Hmlr*|*frontend/src/*Docusign*|*frontend/src/*Sdlt*|*frontend/src/*Searches*)
    ;;
  *)
    printf '%s\n' '{}'
    exit 0
    ;;
esac

# Resolve Core repo root from this script (.cursor/hooks/…), not from cwd.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if ! out="$(python3 "$ROOT/scripts/check_commercial_boundary.py" 2>&1)"; then
  msg="$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
  printf '{"additional_context": %s}\n' "$msg"
  exit 0
fi

printf '%s\n' '{}'
exit 0
