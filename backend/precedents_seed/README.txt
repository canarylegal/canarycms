Bundled precedent library for fresh deployments
================================================

When the `precedent` table is empty and `manifest.json` contains at least one entry
in `precedents`, the backend imports categories + files under `bundle/` on startup
(`app/precedent_bootstrap.py`). An empty `precedents` array does nothing (safe default).

On every startup, missing **global** precedents from the manifest are added by reference
(`sync_missing_global_precedents_from_seed`) so upgrades pick up new universal templates
without overwriting admin edits to existing rows.

**Important:** the full seed runs only when the precedent table has **no rows**. Existing
deployments that already have precedents are updated only for **missing** global references
(`BLANK_LETTER`, `INVOICE_TEMPLATE`, `COMPLETION_STATEMENT`).

Export from a running stack (inherits DATABASE_URL and FILES_ROOT from the container):

  docker compose exec backend python scripts/export_precedent_seed.py

Commit `manifest.json` and `bundle/*` so the next `docker build` includes them.

Regenerate universal templates:

  backend/.venv/bin/python backend/scripts/write_universal_invoice_precedent.py \\
    backend/precedents_seed/bundle/g1_invoice_template.docx

  backend/.venv/bin/python backend/scripts/write_universal_completion_statement_precedent.py \\
    backend/precedents_seed/bundle/g2_completion_statement.docx

Precedent entries with `"global": true` are firm-wide (no category / matter sub-type): for example
the reserved blank letter (`reference`: `BLANK_LETTER`, `kind`: `letter`), invoice template
(`INVOICE_TEMPLATE`), and completion statement template (`COMPLETION_STATEMENT`).
