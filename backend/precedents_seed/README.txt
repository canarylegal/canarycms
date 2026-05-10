Bundled precedent library for fresh deployments
================================================

When the `precedent` table is empty and `manifest.json` contains at least one entry
in `precedents`, the backend imports categories + files under `bundle/` on startup
(`app/precedent_bootstrap.py`). An empty `precedents` array does nothing (safe default).

**Important:** seeding runs only when the precedent table has **no rows**. Existing deployments
that already have precedents are **not** updated from `precedents_seed` on upgrade; use Admin or
scripts (e.g. `set_blank_letter_precedent.py`) for those environments.

Export from a running stack (inherits DATABASE_URL and FILES_ROOT from the container):

  docker compose exec backend python scripts/export_precedent_seed.py

Commit `manifest.json` and `bundle/*` so the next `docker build` includes them.
Categories are matched on the new machine by **matter head type name** and **sub-type name**
(must match Admin matter types).

Precedent entries with `"global": true` are firm-wide (no category / matter sub-type): for example
the reserved blank letter (`reference`: `BLANK_LETTER`, `kind`: `letter`). Export includes these;
scoped precedents still list `category_name`, `matter_sub_type_name`, and `matter_head_type_name`.

---

Wiping users (except admins), cases, case files, and contacts (destructive)

  docker compose exec -e I_CONFIRM_CANARY_WIPE=yes backend python scripts/wipe_except_admin.py

Precedent library rows and files are kept; precedent `file.owner_id` is reassigned to
the first admin user.
