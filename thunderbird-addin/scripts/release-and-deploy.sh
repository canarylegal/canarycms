#!/usr/bin/env bash
# Build, sign, and upload Thunderbird add-on hosting files to TrueNAS SMB share.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${ATN_API_KEY:?Export ATN_API_KEY (from addons.thunderbird.net → API key)}"
: "${ATN_API_SECRET:?Export ATN_API_SECRET}"
: "${SMB_PASSWORD:?Export SMB_PASSWORD (TrueNAS password for ${SMB_USER:-cmcwilli})}"

export CANARY_TB_ARTIFACTS_DIR=".build-out"
export SMB_HOST="${SMB_HOST:-truenas.local}"
export SMB_SHARE="${SMB_SHARE:-thunderbird}"
export SMB_USER="${SMB_USER:-cmcwilli}"

echo "==> Package $(node -p "require('./manifest.json').version")"
npm run package

echo "==> Sign with ATN"
npm run sign

echo "==> Build hosting/ (updates.json + .xpi + .htaccess)"
npm run publish-hosting

echo "==> Upload to smb://${SMB_USER}@${SMB_HOST}/${SMB_SHARE}/"
npm run deploy-smb

echo ""
echo "Done. Verify:"
echo "  https://canarylegalsoftware.co.uk/thunderbird/updates.json"
echo "  https://canarylegalsoftware.co.uk/thunderbird/$(basename hosting/*.xpi)"
