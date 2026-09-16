# Changelog

All notable releases of Canary CMS are documented here. Prefer a tagged release over floating `main` when deploying (see `docs/DEPLOYMENT.md`).

## [Unreleased]

### Added
- Client portal page background is configurable per firm (Admin → Firm details: colour picker + hex); staff UI colours are unchanged.

### Changed
- Structural split of hotspot modules: fat `files`/`portal` routers thinned behind services; `docx_util` packaged by concern; Admin/CaseDetail/Reports/Calendar UI broken into focused modules.
- Frontend Vitest baseline expanded (portal/case helpers, API error detail, navigation) — still unit-level, not E2E.
- Backend unit coverage expanded for Canary Sign / WebDAV / Radicale calendar helpers, portal auth/OTP/grants/forms, and Files / OnlyOffice SSRF + mutate / folder / force-save paths.

### Security
- WebAuthn login begin returns the same HTTP 401 `Invalid credentials` when the account is unknown or has no passkeys (CL-16).
- Case/contact search rejects queries containing NUL bytes with HTTP 400 instead of HTTP 500 (CL-17).
- Invoice approve and void lock the invoice row before ledger mutations (same order) and map deadlocks/stale races to HTTP 409 instead of 500 (CL-13).
- File move takes the matter folder-ops lock and row locks; missing source object or concurrent parent deletion returns HTTP 409 instead of 500 (CL-12).
- After upload into a folder, recursive delete conflicts for a short settle window (and when files are newer than the delete request start) so a concurrent delete cannot remove an object the uploader was just told exists (CL-09).
- Pending ledger approve/edit/reject take a per-pair advisory try-lock and row locks; concurrent loss (including rejection winning an approve race) returns HTTP 409 instead of 500 (CL-14). Simultaneous edit versus approve cannot both succeed — the loser receives HTTP 409 (CL-15).
- Connection pool check-in runs ``pg_advisory_unlock_all()`` then ``rollback`` so session-level folder locks cannot stick on recycled connections (CL-11) without leaving the connection ``INTRANS`` (which caused HTTP 500 on login).
- Recursive folder delete stamps request start and returns HTTP 409 (without deleting) if a non-system file was created after that instant, so a concurrent upload that already returned 201 keeps a durable object (CL-09).
- Upload into a folder holds a session-level folder-ops lock for the whole request (including the byte stream) so concurrent recursive delete returns HTTP 409 while the upload is in flight; destination existence is still checked before commit (CL-09).
- Invoice approval flushes the generated document ``file`` row before linking ``document_file_id``, and wraps document save in a savepoint so a document failure cannot abort financial approval (CL-08). Approval remains idempotent and blocks direct ledger approve/edit/reject of pending invoice-origin pairs.
- Concurrent same-file rename takes a row lock and returns HTTP 409 if the on-disk object was already moved (CL-10).
- Rename/move/delete of checked-out files (and their folders) returns HTTP 409 instead of breaking editor URLs (CL-06).
- Concurrent folder rename is serialized per matter and returns 409 on conflict instead of intermittent 500 (CL-05).
- Desktop/WebDAV edit sessions re-check account active + matter access; disable/deny releases open sessions (CL-07). Browser DocsAPI uses the same WebDAV capability URL; Canary GET/PUT are revoked after deny/disable (open editor tabs may still show a previously fetched copy until closed).
- Staff logout bumps ``auth_token_version`` so bearer JWTs stop working immediately (not only the HttpOnly cookie).
- Staff and firm-default signature uploads decode and re-encode image bytes; HTML labelled as PNG is rejected.
- Portal browse/upload reject `..` and absolute folder inputs with HTTP 400 (was unhandled 500).

### Fixed
- Admin → Storage no longer returns HTTP 500 when the backend has no Docker CLI/`docker.sock` (default notify-only deploy); it reports bind-mount and database sizes with a note that Docker image totals are omitted.
- Documents multi-select Download downloads every selected file (not only the right-clicked one).
- Editing a contact's type or name while an active portal access code exists prompts to revoke that code, so replacing a person on the same contact record cannot silently leave the previous portal login usable.
- Contacts can merge a duplicate global contact into the survivor: matter links and portal grants are moved, both portal codes are revoked, and a fresh client portal code is issued when either side had access (optional e-mail of the new code). Merge is available on the global contact card and on the matter contact edit screen. Before confirming, staff review both contacts side by side (mismatches highlighted) plus the merge impact.
- Cancelling the portal identity warning aborts the save and does not revoke access; a failed portal status load no longer looks like “no access / grant again”.
- Portal client e-mails state why access was granted, name the firm, and explain how to recover if a code fails.
- Portal staff alerts for uploads, completed forms, and quote responses include the matter reference in the subject, a next-step line, and a deep link to open the matter in Canary.
- Matter portal staff notification recipients use a multi-select of Canary users (empty selection keeps fee-earner default).
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
