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
