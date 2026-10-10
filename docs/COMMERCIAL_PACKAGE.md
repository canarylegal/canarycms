# Commercial package

Private product layer for paid connectors (DocuSign, Casera / Searches, HMLR).  
Core stays attachable without it; commercial code loads only when the package is mounted and compatible.

## Layout

| Path | Purpose |
|------|---------|
| `canary-commercial.json` | Package id / version / `requires_canary` / `products` |
| `python/canary_commercial/` | Connector clients, services, settings, FastAPI routers |

ORM models and public API schemas for these products remain in Core (shared with Alembic and the staff UI). Runtime connectors and routers live in the commercial package.

## Attach

```bash
export COMMERCIAL_PACKAGE_DIR=/path/to/canary-commercial
docker compose \
  -f docker-compose.yml \
  -f docker-compose.commercial.example.yml \
  --profile prod up -d
```

Compose sets `COMMERCIAL_PACKAGE_DIR=/commercial` and mounts the package read-only.

## Status

Staff: `GET /commercial-package/status`  
When `attached`, `compatible`, and `loaded` are true, Admin → Integrations and matter Searches / Land Registry surfaces appear.

## Split test

1. Start Core **without** the commercial overlay → Integrations tab hidden; DocuSign/Casera/HMLR routes absent.  
2. Restart **with** the overlay → status `loaded: true`; connectors available.

Local / CI contract (no Compose required):

```bash
export COMMERCIAL_PACKAGE_DIR=/path/to/canary-commercial
./scripts/smoke-commercial-contract.sh
```

Canary Actions: `.github/workflows/commercial-contract.yml` (needs secret `CANARY_COMMERCIAL_TOKEN`).

## Dev habit

| Work | Compose files | Result |
|------|---------------|--------|
| Core-only | `docker-compose.yml` (+ tunnel if needed) — **omit** commercial overlay | Integrations off; Core CI shape |
| Commercial | also `-f docker-compose.commercial.example.yml` with `COMMERCIAL_PACKAGE_DIR` set | Connectors load |

After recreating **frontend**, also recreate tunnel sidecars (`cloudflared-socat` / `cloudflared-dev`) so they share the new network namespace.

## Ownership (current soft boundary)

| Layer | Owns today |
|-------|------------|
| **Commercial** (`canarylegal/canary-commercial`) | Connector clients, services, settings, FastAPI routers (`register.py`) |
| **Core** (`canarylegal/canarycms`) | ORM models, Alembic history, public API schemas, Admin/case UI hosts, soft shims, attach/status API |

See the decision notes in chat / team docs before moving models or UI fully into commercial.
