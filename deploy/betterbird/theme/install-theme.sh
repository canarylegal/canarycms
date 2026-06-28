#!/usr/bin/env bash
# Copy Canary userChrome.css + logo into the newest Betterbird/Thunderbird profile.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${SCRIPT_DIR}/userChrome.css"
LOGO_SRC="${SCRIPT_DIR}/canary-logo.jpg"
TB_ROOT="${HOME}/.thunderbird"
PREF='toolkit.legacyUserProfileCustomizations.stylesheets'

if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi

if [[ ! -d "$TB_ROOT" ]]; then
  echo "No ~/.thunderbird directory found." >&2
  exit 1
fi

PROFILE="$(find "$TB_ROOT" -maxdepth 1 -type d -name '*.default*' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
if [[ -z "$PROFILE" ]]; then
  echo "No *.default* profile under $TB_ROOT" >&2
  exit 1
fi

CHROME="${PROFILE}/chrome"
mkdir -p "$CHROME"
cp "$SRC" "${CHROME}/userChrome.css"
if [[ -f "$LOGO_SRC" ]]; then
  cp "$LOGO_SRC" "${CHROME}/canary-logo.jpg"
fi

USER_JS="${PROFILE}/user.js"
if [[ -f "$USER_JS" ]] && grep -qF "user_pref(\"${PREF}\"" "$USER_JS"; then
  :
else
  {
    echo ""
    echo "// Canary theme — enable profile chrome/userChrome.css"
    echo "user_pref(\"${PREF}\", true);"
  } >> "$USER_JS"
fi

echo "Installed Canary chrome styling to: ${CHROME}/"
echo "  userChrome.css"
[[ -f "${CHROME}/canary-logo.jpg" ]] && echo "  canary-logo.jpg"
echo ""
echo "Restart Betterbird (quit fully, then reopen)."
echo "Also install canary-theme-1.2.0.xpi if not already on v1.2+."
