# Product UI theme (local deploy notes)

Canary’s product theme is a single entry:

- `frontend/src/canary-theme.css` — imports base + surface layer
- `frontend/src/index.css` — **sole `:root` token owner**, shared components, type scale, focus / reduced-motion baselines
- `frontend/src/local-modern.css` — floating chrome / pale wash surfaces (may override chrome pack vars only)

Brand defaults: **DM Sans**, canary yellow primary (`#f0d010`) with dark ink on primary buttons, pale page wash.

Rebuild after theme edits:

```bash
cd /home/colin/canarycms
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod build frontend
GIT_COMMIT=$(git rev-parse HEAD) docker compose --profile prod up -d --force-recreate --no-deps frontend
```
