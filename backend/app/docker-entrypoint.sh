#!/bin/sh
set -e

# Build DATABASE_URL from POSTGRES_* when DATABASE_URL is not provided.
if [ -z "${DATABASE_URL:-}" ]; then
  if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_PASSWORD:-}" ] || [ -z "${POSTGRES_DB:-}" ]; then
    echo "DATABASE_URL is unset and required POSTGRES_* variables are missing." >&2
    exit 1
  fi

  POSTGRES_HOST="${POSTGRES_HOST:-db}"
  POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  ENCODED_PASSWORD="$(python -c "import os, urllib.parse; print(urllib.parse.quote(os.environ['POSTGRES_PASSWORD'], safe=''))")"
  export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${ENCODED_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

# GUI Compose updates run git in-repo; bind-mounted checkouts are often "dubious ownership" (host uid ≠
# container user). Register the mount once at startup so all git versions used in the image accept it.
if command -v git >/dev/null 2>&1 && [ -n "${CANARY_COMPOSE_PROJECT_DIR:-}" ] && [ -d "${CANARY_COMPOSE_PROJECT_DIR}/.git" ]; then
  git config --global --replace-all safe.directory "${CANARY_COMPOSE_PROJECT_DIR}" >/dev/null 2>&1 || true
fi

exec "$@"
