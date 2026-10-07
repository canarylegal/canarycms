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
| `FIRM_MODULE_DIR` | `/firm/module` | Firm module (`manifest.json` + optional `ui/dist` bundle + `migrations/`). Enables published UI slots, firm-schema case state, and lifecycle reactions. |

**Contract smoke (Phase 7 MVP):** with a package attached, run `make smoke-firm-contract` (or `make smoke-firm-contract-ci` on an empty DB). See [`TESTING.md`](./TESTING.md).

Branding files (letterheads, logos, portal background) live under the firm package `assets/` tree. Configure them in Admin today; keep the files in the package for ops and future seed hooks.

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
  assets/
    letterheads/
    quote-letterheads/
    logos/
    portal-background/
  scripts/          # optional firm helpers
  compose/          # optional firm-only snippets
  README.md
```

Copy [canarylegal/example-firm-package-template](https://github.com/canarylegal/example-firm-package-template) (private) as a starting point. See [canarylegal/example-firm-pilot](https://github.com/canarylegal/example-firm-pilot) for a module + UI reference.

## What stays in public Canary

- The six system precedents  
- Portal **forms engine** and Admin/UI to build forms  
- Published firm **slots** and `/firm-modules/*` APIs  
- Fictional/sample generators for tests (no real firms)  
- This document and the example compose overlay  

Firm form **definitions**, firm precedents beyond the system six, and firm **UI** do not ship in the kernel.

## Hygiene

Public `.gitignore` already ignores firm-shaped local scripts (`seed_*_portal_forms.py`, firm precedent deploy helpers, Betterbird firm policies). Prefer putting those under the firm package instead of the Canary tree.
