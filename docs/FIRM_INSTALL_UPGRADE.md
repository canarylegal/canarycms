# Install and upgrade: Canary + firm package (Phase 6)

Customer shape:

1. **Pinned Canary** images / release tag (CMS **2.0** line)  
2. **Firm package** private repo (with `canary-firm.json`)  
3. **Compose overlay** mounting the package read-only  

Do **not** edit Canary source for firm customisation.

## Prerequisites

- Docker Compose host  
- Firm package path containing `canary-firm.json`  
- `.env` with secrets (see `.env.example`)  

## Install (first time)

```bash
export FIRM_PACKAGE_DIR=/path/to/your-firm-package
cd /path/to/canarycms
git checkout v2.0.0   # or your pinned CMS tag
GIT_COMMIT=$(git rev-parse HEAD) \
CANARY_PRODUCT_VERSION=2.0.0 \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.firm.example.yml \
    --profile prod up -d --build
```

Startup order (backend):

1. `python -m app.firm_module_migrate` — firm module SQL (skipped if package incompatible)  
2. `alembic upgrade head` — core schema (includes catalogue schema ``firm``)  
3. API process (boot-merge firm package seeds into ``firm`` when attached)

**Detach** the firm layer (does not happen on unmount alone): see [`FIRM_PACKAGE.md`](./FIRM_PACKAGE.md) — preflight / force via `/firm-package/detach` or `python -m app.firm_detach`.  

## Compatibility

`canary-firm.json` must declare:

| Field | Example |
|-------|---------|
| `package_id` | `example_firm_pilot` |
| `package_version` | `1.0.0` (semver; also tag the git repo) |
| `requires_canary` | `>=2.0.0 <3.0.0` |

`CANARY_PRODUCT_VERSION` on the Canary install must satisfy that range.

**If incompatible:** Canary core still runs; firm module / firm migrations are refused; all staff see a **red “!”** instead of the Canary mark in the side menu (hover/click for detail). Admins see the same under **Admin → Deploy → Firm package**.

## Upgrade Canary

```bash
cd /path/to/canarycms
git fetch --tags
git checkout v2.x.y          # new pin; stay within firm requires_canary
# Confirm canary-firm.json still allows this product version
GIT_COMMIT=$(git rev-parse HEAD) \
CANARY_PRODUCT_VERSION=2.x.y \
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.firm.example.yml \
    --profile prod up -d --build
```

Checklist:

1. Read firm `requires_canary`  
2. Bump Canary pin only if compatible (or bump firm package first)  
3. Rebuild with `GIT_COMMIT` + matching `CANARY_PRODUCT_VERSION`  
4. Firm migrate runs, then core Alembic  

## Upgrade firm package

```bash
cd /path/to/your-firm-package
git fetch --tags
git checkout v1.x.y          # new package_version
# Ensure canary-firm.json requires_canary still matches running Canary
docker compose … up -d       # remount / recreate backend so migrate + manifest reload
```

## Admin notify-only

- **Admin → Deploy → Check for updates** — Canary image vs GitHub (existing)  
- **Admin → Deploy → Firm package** — mounted package id/version/compat  

No in-app Compose apply (no Docker socket).

## Survival / contract tests (Phase 7 / 7b)

Before upgrading Canary under a firm package:

```bash
make smoke-firm-contract-ci   # or make smoke-firm-contract on a populated DB
PREV_TAG=v2.0.0 make smoke-firm-dual-tag   # previous release → current + firm
```

See [`TESTING.md`](./TESTING.md) (Firm contract smoke). CI workflow:
`.github/workflows/firm-contract.yml` (needs secret `EXAMPLE_FIRM_PILOT_TOKEN`;
optional `workflow_dispatch` input `prev_tag` for dual-tag).

## Related

- Public attach contract: [`FIRM_PACKAGE.md`](./FIRM_PACKAGE.md)  
- Module contract (private): `FIRM_MODULE_CONTRACT.md`  
- Overlay: [`docker-compose.firm.example.yml`](../docker-compose.firm.example.yml)  
