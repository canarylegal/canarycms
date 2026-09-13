# Changelog

All notable releases of Canary CMS are documented here. Prefer a tagged release over floating `main` when deploying (see `docs/DEPLOYMENT.md`).

## [Unreleased]

### Security
- Portal browse/upload reject `..` and absolute folder inputs with HTTP 400 (was unhandled 500).
- Staff and firm-default signature uploads decode and re-encode image bytes; HTML labelled as PNG is rejected.
- Staff logout bumps ``auth_token_version`` so bearer JWTs stop working immediately (not only the HttpOnly cookie).
- Desktop/WebDAV edit sessions re-check account active + matter access; disable/deny releases open sessions (CL-07). Browser DocsAPI uses the same WebDAV capability URL; Canary GET/PUT are revoked after deny/disable (open editor tabs may still show a previously fetched copy until closed).
- Rename/move/delete of checked-out files (and their folders) returns HTTP 409 instead of breaking editor URLs (CL-06).
- Concurrent folder rename is serialized per matter and returns 409 on conflict instead of intermittent 500 (CL-05).
- Upload into a folder holds a session-level folder-ops lock for the whole request (including the byte stream) so concurrent recursive delete returns HTTP 409 while the upload is in flight; destination existence is still checked before commit (CL-09).
- Invoice approval flushes the generated document ``file`` row before linking ``document_file_id``, and wraps document save in a savepoint so a document failure cannot abort financial approval (CL-08). Approval remains idempotent and blocks direct ledger approve/edit/reject of pending invoice-origin pairs.
- Concurrent same-file rename takes a row lock and returns HTTP 409 if the on-disk object was already moved (CL-10).

### Ops / release readiness
- Admin → Deploy defaults to **`latest-release`** (compare to newest GitHub Release tip, not floating `main`).
- Backend rejects `.env.example` `CHANGE_ME_*` / all-`#` secret placeholders at startup.
- Go-live checklist and README quick start require generated secrets and tag-pinned checkouts.
- Portal smoke workflow runs on `v*` tags and on compose/backend image path changes; healthier wait/logging.
- Fix duplicate Alembic revision id that blocked cold `alembic upgrade head` (portal smoke / fresh installs).

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
