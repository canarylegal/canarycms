# Attaching a firm package

Canary’s public repository is the **product kernel**. Firm-specific letterheads, extra precedents, portal form definitions, firm UI modules, and deploy helpers belong in a **private sibling package** mounted beside a pinned Canary release — not in `canarycms` source.

Architecture detail for maintainers is kept internally. This page is the public attach contract.

## Shape

A customer install is:

1. **Pinned Canary** (release tag / images) — unchanged source  
2. **Firm package** — private git repo or directory tree with root `canary-firm.json`  
3. **Compose overlay** — mounts and env (no secrets in the example file)

Install/upgrade runbook: [`FIRM_INSTALL_UPGRADE.md`](./FIRM_INSTALL_UPGRADE.md).

## Published mount hooks

| Environment variable | Mount (example) | Behaviour |
|----------------------|-----------------|-----------|
| `PRECEDENTS_SEED_DIR` | Canary image default `/app/precedents_seed` | System precedents (six global templates). Do **not** replace this with firm content. |
| `FIRM_PRECEDENTS_SEED_DIR` | `/firm/precedents` | Additive firm precedents (`manifest.json` + `bundle/`). Missing references imported on startup. |
| `PORTAL_FORMS_SEED_DIR` | `/firm/portal-forms` | Firm portal form templates (`manifest.json`). Missing references imported on startup. |
| `PORTAL_FORMS_SEED_REPAIR` | — | If `1`/`true`/`yes`, refresh fields on existing templates from the seed (destructive to admin edits). |
| `FEE_SCALES_SEED_DIR` | `/firm/fee-scales` | Firm fee scale templates (`manifest.json`). Missing references imported on startup. |
| `FEE_SCALES_SEED_REPAIR` | — | If `1`/`true`/`yes`, replace categories/lines/bands on existing scales from the seed. |
| `FIRM_MATTER_TYPES_SEED_DIR` | `/firm/matter-types` | Firm matter-type catalogue (`seed.json`). Core ships no product types; missing heads/subs merged on startup. |
| `FIRM_ASSETS_SEED_DIR` | `/firm/assets` | Branding files under `letterheads/`, `quote-letterheads/`, `logos/`, `portal-background/`. Seeds Admin firm-settings slots when empty (never clobbers Admin uploads). |
| `FIRM_MODULE_DIR` | `/firm/module` | Firm module (`manifest.json` + optional `ui/dist` bundle + `migrations/`). Enables published UI slots, firm-schema case state, and lifecycle reactions. |

**Contract smoke (Phase 7 / 7b):** with a package attached, run `make smoke-firm-contract` (or `make smoke-firm-contract-ci` on an empty DB). Dual-tag upgrade: `PREV_TAG=vX.Y.Z make smoke-firm-dual-tag`. See [`TESTING.md`](./TESTING.md).

Portal form field types include `checkbox` (boolean; required = must be checked), `file` (one upload), and `files` (multiple uploads on one field, max 20).

## Firm module (Phase 4)

When `FIRM_MODULE_DIR` points at a module directory:

- **Manifest** (`manifest.json`, `version: 1`) — module id, matter-type scope, stages/checklist config, `ui` + `slots`
- **UI bundle** — build-time IIFE under `ui/dist/` (e.g. `firm-module.js`), served same-origin at `/firm-modules/active/ui/…`. **Not** remote third-party JavaScript.
- **HTTP API** — `/firm-modules/active`, `/active/pipeline`, `/active/matters/{case_id}`
- **Lifecycle** — transactional outbox in core (`lifecycle.matter.created`, `lifecycle.document.uploaded`, `lifecycle.matter.status_changed` on closed/archived)
- **Storage** — firm case state in a firm Postgres schema (default: same DB, e.g. `firm_example_pilot.case_state`); migrations under `module/migrations/` applied by `python -m app.firm_module_migrate` before core Alembic

Published UI slots (manifest `slots` / `ui.exports`):

| Slot | Mount point | Pilot |
|------|-------------|-------|
| `matter_panel` | Matter left-nav panel | Used |
| `dashboard_widget` | Main-menu cases panel | Used |
| `matter_actions` | Beside matter panel | Stub host |
| `portal_section` | Portal hub | Stub host |
| `admin_page` | Admin → Firm details | Stub host |

Firm UI receives host props (`token`, `caseId`, `apiFetch`, …) and must not import Canary internals.

## Example compose overlay

See [`docker-compose.firm.example.yml`](../docker-compose.firm.example.yml) in the Canary root:

```bash
# Clone or copy a firm package (private). Template:
#   https://github.com/canarylegal/example-firm-package-template  (private)
export FIRM_PACKAGE_DIR=/path/to/your-firm-package

docker compose \
  -f docker-compose.yml \
  -f docker-compose.firm.example.yml \
  --profile prod up -d
```

The overlay mounts `${FIRM_PACKAGE_DIR}` read-only at `/firm` and sets the env vars above.

## Firm package layout (recommended)

```
your-firm-package/
  canary-firm.json        # package id, version, requires_canary (Phase 6)
  module/                 # optional firm module
    manifest.json
    migrations/versions/  # firm-owned SQL (Phase 5)
    ui/
      src/
      dist/firm-module.js
  precedents/
    manifest.json
    bundle/
  portal-forms/
    manifest.json
  fee-scales/
    manifest.json
  matter-types/
    seed.json
  assets/
    letterheads/          # *.docx → firm letterhead when unset
    quote-letterheads/    # *.docx → quote letterhead when unset
    logos/                # png/jpeg/webp → portal logo when unset
    portal-background/    # png/jpeg/webp → portal background when unset
  scripts/          # optional firm helpers
  compose/          # optional firm-only snippets
  README.md
```

Copy [canarylegal/example-firm-package-template](https://github.com/canarylegal/example-firm-package-template) (private) as a starting point. See [canarylegal/example-firm-pilot](https://github.com/canarylegal/example-firm-pilot) for a module + UI reference.

## What stays in public Canary

- Portal **forms engine** and Admin/UI to build forms (runtime submissions stay in core)  
- Published firm **slots** and `/firm-modules/*` APIs  
- Fictional/sample generators for tests (no real firms)  
- This document and the example compose overlay  
- Users, cases, file **bytes/metadata**, integrations  

Firm form **definitions**, precedents (including kernel-seeded system six rows), fee scales, matter types, and firm **UI** are firm-layer data — see below.

## Firm catalogue schema (`firm`)

Catalogue data lives in Postgres schema **`firm`** (always created by core migrations), not in `public`. API connections set `search_path` to `public, firm` so application SQL stays unqualified:

| Firm-owned | Core (`public`) |
|------------|-----------------|
| Matter head/sub types, menus, standard tasks, event templates | Users, cases (nullable FKs into `firm` matter types) |
| Fee scales (+ categories/lines/bands) | `user_fee_scale_favorite` |
| Portal form **templates** + fields | Portal form **submissions** |
| Precedents + categories (system six seed files ship in the image; rows live in `firm`) | File storage rows/bytes |
| Branding slots on `firm_settings` (cleared on force-detach) | `firm_settings` singleton row |
| Firm module schema (`storage.schema`, e.g. `firm_*`) + `case_state` | Lifecycle outbox |

**Boot-merge (every startup when the package is attached and compatible):** insert missing package refs; do not overwrite Admin edits unless `*_SEED_REPAIR`; branding slots seed only when empty; Admin-created extras are never deleted on boot. If the package is absent, firm seeds are skipped and existing `firm` data is left alone until an explicit detach.

## Detach

Unmounting the package volume does **not** wipe the database. Use an explicit detach:

- **Preflight (admin):** `GET /firm-package/detach/preflight` — blocked while any case still has matter types set, firm-module `case_state` rows exist, or portal submissions exist.
- **Detach:** `POST /firm-package/detach` with `{"force": false}` — only when preflight is clear; then wipes unused catalogue.
- **Force detach (sandboxes):** `POST /firm-package/detach` with `{"force": true, "confirm": true}`, or CLI:

```bash
I_CONFIRM_FIRM_DETACH=yes python -m app.firm_detach --force
```

Force nulls case matter-type FKs, deletes firm catalogue rows and portal submissions, clears branding slots, and drops firm-module schemas. Re-attach by remounting the package and restarting (boot-merge re-seeds).

**Matter type snapshots:** each case stores `matter_head_type_name` / `matter_sub_type_name` (stable labels). Detach clears live FKs but keeps those names; on the next attach/boot, Canary restores FKs by matching names in the firm catalogue.

## Hygiene

Public `.gitignore` already ignores firm-shaped local scripts (`seed_*_portal_forms.py`, firm precedent deploy helpers, Betterbird firm policies). Prefer putting those under the firm package instead of the Canary tree.
