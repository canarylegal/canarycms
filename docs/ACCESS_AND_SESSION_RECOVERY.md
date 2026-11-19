# Access, audit and session recovery

This release preserves the existing matter-list policy (a firm-wide staff directory),
layout and double-click/right-click controls. Opening a restricted matter or accessing
its documents still requires the matter permission check; changing a file ID does not
change its owning matter. Access rules remain managed by the fee earner or administrator.

## Document controls

- Unknown matter access modes fail closed.
- A user may release their own edit sessions, but cannot clear another editor's pending
  save or advance its version, even if they may access the same matter.
- Publishing a pending composed document and exporting an editor PDF require the caller's
  active edit session. Browser-persist checks authorisation again after downloading bytes
  from ONLYOFFICE, so a revocation during that download prevents persistence.
- Existing WebDAV and ONLYOFFICE callback checks continue to enforce active ownership,
  current matter permissions and document-key binding. Cross-user API tests cover denied
  read/list/export/rename/move/delete/checkout/save calls, swapped matter/file IDs and
  revocation of an already issued WebDAV session.

## Audit

Authenticated HTTP 403 responses produce `access.denied` after rolling back the rejected
transaction. The new audit transaction commits no rejected business mutations. Metadata
contains the HTTP method, route template and relevant path identifiers; request bodies,
query strings, credentials, document contents and exception details are excluded.
Successful document reads add `case.file.read`. Validated callback saves identify the
edit-session owner; browser-persist saves identify the authenticated caller. Existing
permission grant/revoke events remain, with integration checks proving they are recorded.
File deletion no longer commits its database row removal before its audit event is queued.
Filesystem writes are not transactional with PostgreSQL; backup/recovery remains necessary.

## Session expiry

A 401 from an operation no longer reloads the main application. A recovery notice appears
only when needed and leaves the matter/editor and local drafts mounted. Sign in in a new
tab with the same account, return and check the session, then explicitly retry. Uploads
retain the selected File objects and acknowledged-file progress while the retry dialog
is open; already acknowledged uploads are not replayed. Cancelling abandons the pending
selection. Network-ambiguous uploads are still reconciled rather than blindly retried.
No passwords or document contents are written to local storage. A full browser reload
still loses in-memory work; do not close the original tab while recovering.

## ONLYOFFICE CI readiness

The pinned document-server image initially serves `/healthcheck`, then regenerates fonts
and restarts docservice/converter. That gap caused a save command to receive 502. The
isolated test stack now also waits for the image's final log-tail process, reached only
after fonts and gzip startup work. Optional online plugin updates are disabled in
the disposable test stack. This is deliberately tied to the pinned image's
startup script; recheck the readiness condition when upgrading the image. Browser tests
still verify saved DOCX bytes and do not hide failures with automatic test retries.
