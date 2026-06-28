#!/usr/bin/env bash
# Reset a self-hosted Canary compose checkout to match origin (e.g. after a force-pushed Git history rewrite).
# Run on the deployment host (not inside a container). Safe for tracked files only — see .env.example.
set -euo pipefail

PROJECT_DIR="${1:-${CANARY_COMPOSE_HOST_PROJECT_DIR:-/opt/canarycms}}"
REF="${CANARY_GITHUB_DEPLOY_REF:-main}"

if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
  echo "No git repo at ${PROJECT_DIR}" >&2
  exit 1
fi

git -c "safe.directory=${PROJECT_DIR}" -C "${PROJECT_DIR}" fetch origin "${REF}"
git -c "safe.directory=${PROJECT_DIR}" -C "${PROJECT_DIR}" reset --hard "origin/${REF}"
echo "Reset ${PROJECT_DIR} to origin/${REF}: $(git -C "${PROJECT_DIR}" rev-parse --short HEAD)"
