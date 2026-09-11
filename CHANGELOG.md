# Changelog

All notable releases of Canary CMS are documented here. Prefer a tagged release over floating `main` when deploying (see `docs/DEPLOYMENT.md`).

## [1.0.0] — 2026-09-11

First named production baseline. Active development continues; `1.x` will move with minor/patch releases.

### Highlights
- **CI green** on `main` (backend pytest, frontend Vitest/build, Thunderbird lint/package).
- **Notify-only Admin → Deploy** — no in-app “Update now”; backend does not mount `docker.sock`. Host/SSH or CI applies updates.
- **Production hardening** from the preceding `main` line (session cookie posture, compose bind defaults, related security work).
- **Frontend maintainability** — App shell and CaseDetail split into focused modules with lazy routes where useful.
- **Matter exchange portal** access included in the hardened baseline.

### Operator notes
- Pin deploys to this tag (`v1.0.0`), not an unreviewed `main` tip.
- Former GUI Compose updater code is retained fail-closed on purpose; see module docs under `backend/app/local_compose_update.py` and `docs/DEPLOYMENT.md`.
- Thunderbird add-in versioning remains separate (`thunderbird-addin` / `thunderbird-v*` workflow).

[1.0.0]: https://github.com/canarylegal/canarycms/releases/tag/v1.0.0
