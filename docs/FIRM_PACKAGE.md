# Attaching a firm package

Canary’s public repository is the **product kernel**. Firm-specific letterheads, extra precedents, portal form definitions, and deploy helpers belong in a **private sibling package** mounted beside a pinned Canary release — not in `canarycms` source.

Architecture detail for maintainers is kept internally. This page is the public attach contract.

## Shape

A customer install is:

1. **Pinned Canary** (release tag / images) — unchanged source  
2. **Firm package** — private git repo or directory tree  
3. **Compose overlay** — mounts and env (no secrets in the example file)

## Published mount hooks

| Environment variable | Mount (example) | Behaviour |
|----------------------|-----------------|-----------|
| `PRECEDENTS_SEED_DIR` | Canary image default `/app/precedents_seed` | System precedents (six global templates). Do **not** replace this with firm content. |
| `FIRM_PRECEDENTS_SEED_DIR` | `/firm/precedents` | Additive firm precedents (`manifest.json` + `bundle/`). Missing references imported on startup. |
| `PORTAL_FORMS_SEED_DIR` | `/firm/portal-forms` | Firm portal form templates (`manifest.json`). Missing references imported on startup. |
| `PORTAL_FORMS_SEED_REPAIR` | — | If `1`/`true`/`yes`, refresh fields on existing templates from the seed (destructive to admin edits). |
| `FIRM_MODULE_DIR` | `/firm/module` | Phase 3 firm module (`manifest.json`). Enables matter tab, pipeline widget, matter-created seed. |

Branding files (letterheads, logos, portal background) live under the firm package `assets/` tree. Configure them in Admin today; keep the files in the package for ops and future seed hooks.

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

Copy [canarylegal/example-firm-package-template](https://github.com/canarylegal/example-firm-package-template) (private) as a starting point. It includes illustrative precedents and sterilised example portal forms — replace them for a real firm.

## What stays in public Canary

- The six system precedents  
- Portal **forms engine** and Admin/UI to build forms  
- Fictional/sample generators for tests (no real firms)  
- This document and the example compose overlay  

Firm form **definitions** and firm precedents beyond the system six do not ship in the kernel.

## Hygiene

Public `.gitignore` already ignores firm-shaped local scripts (`seed_*_portal_forms.py`, firm precedent deploy helpers, Betterbird firm policies). Prefer putting those under the firm package instead of the Canary tree.
