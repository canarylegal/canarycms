# Commercial schema ownership

Historical DocuSign / Casera / HMLR / search-provider revisions in
`versions/` remain for installs that already applied them.

**Do not add new vendor DDL here.** Add numbered SQL under
`canary-commercial/module/migrations/versions/` instead
(`python -m app.commercial_module_migrate` runs before `alembic upgrade head`).
