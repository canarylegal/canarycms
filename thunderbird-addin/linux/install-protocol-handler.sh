#!/usr/bin/env bash
# Register canary-eml: so browsers (esp. Firefox) can launch Thunderbird when it is closed.
set -euo pipefail

DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DEST="$DEST_DIR/canary-eml.desktop"
SRC="$(cd "$(dirname "$0")" && pwd)/canary-eml.desktop"

if ! command -v thunderbird >/dev/null 2>&1; then
  echo "thunderbird not found on PATH; install Thunderbird first." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
install -m 644 "$SRC" "$DEST"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DEST_DIR" >/dev/null 2>&1 || true
fi

if command -v xdg-mime >/dev/null 2>&1; then
  xdg-mime default canary-eml.desktop x-scheme-handler/canary-eml
fi

echo "Registered canary-eml: → Thunderbird ($DEST)"
xdg-mime query default x-scheme-handler/canary-eml 2>/dev/null || true
