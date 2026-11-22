#!/usr/bin/env bash
# Retired: deliberately performs no Docker, filesystem or deployment operations.
set -euo pipefail
cat >&2 <<'NOTICE'
This legacy command is retired because it cannot safely recover a complete installation.
Use scripts/operations.py with a private reviewed configuration for paired backups.
Use scripts/recovery_drill.py --require-complete to restore into NEW isolated volumes.
See docs/OPERATIONS.md and docs/DISASTER_RECOVERY.md. No changes were made.
NOTICE
exit 2
