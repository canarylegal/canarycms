# Commercial schema ownership

Historical DocuSign / Casera / HMLR / search-provider revisions in
`versions/` remain for installs that already applied them. Those filenames are
frozen in `scripts/check_commercial_boundary.py`.

**Do not add new vendor DDL here.** Add numbered SQL under
`canary-commercial/module/migrations/versions/` instead
(`python -m app.commercial_module_migrate` runs before `alembic upgrade head`).

ORM model classes for those tables may still live under `backend/app/models/`
(shared persistence / Alembic history); runtime routers and UI do not.