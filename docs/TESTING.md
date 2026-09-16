# Testing Canary

## Unit tests

```bash
make test-backend
# or: cd backend && pytest -q
```

These run in CI on every push/PR (see `.github/workflows/ci.yml`).

## Portal smoke (quote / form / Canary Sign)

End-to-end HTTP checks against a **running** Docker backend (`scripts/smoke_portal_flows.py`).

```bash
# Stack must already be up (e.g. docker compose --profile prod up -d)
make smoke-portal

# Empty / CI-style DB: create matter 000002 + Sam Thomas first
make smoke-portal-ci

# Also refresh demo pending items
./scripts/smoke-portal.sh --seed

# Void leftover pending quote/form/sign for Sam on 000002, re-seed, then smoke
make smoke-portal-reset
# or: ./scripts/smoke-portal.sh --reset-demo
```

Demo seed writes valid blank PDFs (pikepdf). `reset_portal_demo.py` requires `I_CONFIRM_CANARY_SEED=yes` (the smoke wrapper sets it).

Environment overrides:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CASE_NUMBER` | `000002` | Matter under test |
| `PORTAL_SMOKE_BASE` | `http://127.0.0.1:8000` | Backend URL (inside container) |

CI: `.github/workflows/portal-smoke.yml` builds `db`+`backend`, ensures the fixture, and runs the same smoke script on portal-related path changes and via **workflow_dispatch**.

Frontend CI runs `npm test` (Vitest) then `npm run build` (TypeScript + Vite). `npm run lint` exists but currently fails on substantial pre-existing React Compiler / eslint debt — wire it into CI only after a dedicated lint cleanup.

### Frontend unit tests

```bash
cd frontend && npm test
# or: npm run test:watch
```

Vitest covers pure helpers and a few UI seams (not E2E): portal background/contrast, case finance totals, folder path codec, office/e-mail file detection, doc list formatting, matter labels / close-matter balance checks, portal folder sharing copy, API error humanization, app navigation parse/build/sanitize, dialog queue, contact merge / portal identity guards, and related session / main-menu helpers. Prefer unit tests without heavy network mocks unless a thin `apiFetch` stub is enough.

## Live security checks

```bash
make smoke-security
```

Runs `backend/scripts/live_security_verify.py` inside the backend container.
