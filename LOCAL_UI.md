# Local UI modernisation (this machine only)

These changes live under `/home/colin/canarycms` and are **not** intended for GitHub.

Files of note:
- `frontend/src/local-modern.css`
- `frontend/src/main.tsx` (imports the CSS)
- `frontend/src/AppSidebar.tsx` (persisted expand/collapse)
- `frontend/src/case/CaseDetail.tsx` (case left rail)
- `frontend/src/AdminConsole.tsx` (admin tab strip)

Rebuild after edits:

```bash
cd /home/colin/canarycms
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build frontend
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod up -d --force-recreate --no-deps frontend
```
