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

Frontend CI runs `npm run lint:ci` (eslint, zero errors; warnings capped), `npm test` (Vitest), then `npm run build` (TypeScript + Vite). React Compiler / Fast Refresh / `no-explicit-any` debt remains as **warnings** with a `--max-warnings` ratchet in `lint:ci` — lower the cap when cleaning a slice.

### Browser E2E (Playwright)

Thin Chromium smoke against a **running** frontend+backend (not part of the default unit CI job):

```bash
# Stack UI on :8080; firm staff recommended for matter-open path
export BASE_URL=http://127.0.0.1:8080
export E2E_STAFF_EMAIL='…'
export E2E_STAFF_PASSWORD='…'
make test-e2e
# or: cd frontend && npm run test:e2e
```

Covers staff password login (main menu or master recovery shell), optional open-first-matter → docs panel, and portal `/portal` sign-in chrome. CI: `.github/workflows/browser-e2e.yml` (path-filtered + `workflow_dispatch`) brings up compose `prod`, ensures the portal fixture staff user, and runs Playwright.

### Frontend unit tests

```bash
cd frontend && npm test
# or: npm run test:watch
```

Vitest covers pure helpers and a few UI seams (not E2E): portal background/contrast, case finance totals, folder path codec, office/e-mail file detection, doc list formatting, matter labels / close-matter balance checks, portal folder sharing copy, API error humanization, app navigation parse/build/sanitize, dialog queue, contact merge / portal identity guards, and related session / main-menu helpers. Prefer unit tests without heavy network mocks unless a thin `apiFetch` stub is enough.

Backend `pytest` also covers (unit / service level, not full HTTP E2E):
- **Canary Sign / WebDAV / Radicale** — envelope PDF helpers, WebDAV path/auth/PROPFIND helpers, ICS parse + calendar access, htpasswd sync
- **Portal** — OTP mint/verify, portal auth service, grant expiry/path rules, form complete + PDF fill
- **Files / OnlyOffice** — callback SSRF URL checks, editable type sets, case file mutate/folder services, force-save wait/command

## Live security checks

```bash
make smoke-security
```

Runs `backend/scripts/live_security_verify.py` inside the backend container.
