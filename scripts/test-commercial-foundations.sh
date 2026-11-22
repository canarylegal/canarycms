#!/usr/bin/env bash
# Build and run only a uniquely named disposable stack, with no host credentials.
set -euo pipefail
cd "$(dirname "$0")/.."
project="canary-commercial-test-$(date +%s)-$$"
compose=(docker compose --env-file /dev/null -p "$project" -f docker-compose.commercial-test.yml)
cleanup() {
  status=$?
  trap - EXIT
  "${compose[@]}" down --volumes --remove-orphans
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" build tests
"${compose[@]}" up -d --wait db
"${compose[@]}" run --rm --no-deps tests
