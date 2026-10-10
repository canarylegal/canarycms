# Commercial package (Level C)

Private product layer for paid connectors (DocuSign, Casera / Searches, HMLR).  
Core attaches the package at `/commercial`; without it, Core boots and those products are omitted (no routers, no UI bundle).

## Layout (`canarylegal/canary-commercial`)

| Path | Purpose |
|------|---------|
| `canary-commercial.json` | Package id / version / `requires_canary` / `products` |
| `python/canary_commercial/` | Connector clients, services, FastAPI routers |
| `module/manifest.json` | UI slots + storage schema for migrations |
| `module/ui/dist/commercial-module.js` | IIFE UI bundle (Admin / matter / DocuSign) |
| `module/migrations/versions/` | Commercial-owned SQL (after Core Alembic history) |

## Ownership

| Layer | Owns |
|-------|------|
| **Commercial** | Connector runtime, routers, UI IIFE, **all new** vendor DDL |
| **Core** | Attach/status APIs, thin UI hosts, historical Alembic, ORM table definitions (shared persistence), soft shims |

### Where new work goes

| Change | Put it in |
|--------|-----------|
| Casera / HMLR / DocuSign / Searches UI | `canary-commercial/module/ui` (slot export) |
| Connector API / client / router | `canary-commercial/python/canary_commercial` |
| New vendor tables / columns | `canary-commercial/module/migrations/versions/*.sql` |
| Core attach sockets, slot hosts, soft shims | Core only |

Do **not** add Core Alembic revisions for vendor DDL, reintroduce Admin/matter DocuSign–Searches–HMLR components under `frontend/src/`, or add `*casera*` / `*hmlr*` / `*docusign*` routers under `backend/app/routers/`.

CI enforces this via `scripts/check_commercial_boundary.py` (job `commercial-boundary`).

## Attach

```bash
export COMMERCIAL_PACKAGE_DIR=/path/to/canary-commercial
docker compose \
  -f docker-compose.yml \
  -f docker-compose.commercial.example.yml \
  --profile prod up -d
```

Sets `COMMERCIAL_PACKAGE_DIR=/commercial` and `COMMERCIAL_MODULE_DIR=/commercial/module`.

Boot order: `commercial_module_migrate` → `firm_module_migrate` → `alembic upgrade head` → API.

## Status / UI

- Staff: `GET /commercial-package/status`
- Module: `GET /commercial-modules/active` (+ `/active/ui/{file}` for the IIFE)
- When attached + compatible + loaded: Admin → Integrations and matter Searches / Land Registry / DocuSign surfaces mount commercial slot components.

## Dev habit

| Work | Compose |
|------|---------|
| Core-only | Omit commercial overlay |
| Commercial | Include `docker-compose.commercial.example.yml` + `COMMERCIAL_PACKAGE_DIR` |

Rebuild commercial UI after editing `module/ui/src`:

```bash
cd module/ui && npm install && npm run build
```

After recreating **frontend**, also recreate `cloudflared-socat` / `cloudflared-dev`.

## Contract smoke

```bash
export COMMERCIAL_PACKAGE_DIR=/path/to/canary-commercial
./scripts/smoke-commercial-contract.sh
```

Actions: `.github/workflows/commercial-contract.yml` (secret `CANARY_COMMERCIAL_TOKEN`).
