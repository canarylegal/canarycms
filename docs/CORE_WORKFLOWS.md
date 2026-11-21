# Core workflow regression tests

Run from the checkout with Docker and Docker Compose installed:

```sh
make test-deploy
make test-core-workflows
```

The workflow runner creates a uniquely named Compose project from `docker-compose.core-test.yml`. It uses its own PostgreSQL database, document volume, ONLYOFFICE instance and browser runner; it does not use the normal `.env`, publish ports, or mount deployment data. Cleanup removes **only this test project's** containers and volumes, including on test failure. Evidence is written to `artifacts/core-workflows/` (override with an absolute `CORE_TEST_OUTPUT`).

The seed script requires both `CANARY_TEST_FIXTURE=1` and a database name ending `_core_test`. It refuses existing non-fixture users. Never point it at a real database. Synthetic passwords in the standalone test configuration are only for this isolated, unexposed stack.

## Required checks

- Staff password login, matter opening by double-click, right-click menus, Escape/focus restoration, and logout/session rejection.
- Actual browser document upload, ONLYOFFICE opening/editing, Save Changes, download and verification that the saved text exists in the downloaded DOCX.
- A restricted user receives 403 for matter, documents and ledger access.
- A user with anticipated-posting rights creates a pending anticipated client receipt; it does not affect the approved balance. Approval without actual posting rights is denied. A separate approver approves it and the balance changes by the exact amount. A deficit posting is rejected without changing the balance.
- The client-portal sign-in screen renders.

Tests fail rather than skip when credentials or fixtures are missing. They run against PostgreSQL and real services, not HTTP mocks. The workflow executes on every PR, every main update, release tags and manual dispatch. Configure the `core-workflows` check as required in repository branch protection; changing branch protection is a separate repository-administration action.

The Playwright runner image is pinned to `v1.55.0-noble`, matching the lockfile's `@playwright/test`. Update both together. Screenshots/traces and service logs are retained as CI artifacts. The test stack is isolated, but those artifacts should still be treated as internal diagnostics.

These checks cover the core release path. They do not replace broader unit tests, concurrency/load testing, financial reconciliation tests or a security audit.

## Document failure paths

The browser suite also injects failures into otherwise real document workflows:

- Reject the second upload in a batch with HTTP 429, then retry using the retained file selection. Verify the first upload is not repeated.
- Accept an upload on the server but lose its response. Verify the client reconciles the document list instead of creating a duplicate.
- Deny a download with HTTP 403, then test a separate transient failure and retry through the existing dialog.
- Deny the editor's first save attempt, retry without reopening or retyping, and verify the edited text in the downloaded DOCX.

Unit tests cover read retry limits, body timeouts, expired sessions/access denial, partial batch progress, duplicate upload suppression, folder changes during retry, portal notification failures and save-confirmation polling.

Transfer requests and browser delivery are in `documentRequests.ts` and `documentTransferOps.ts`; `useCaseDocumentTransfers.ts` owns progress, busy state and retry dialogs. Reads retry at most once automatically. Uploads never retry automatically. Matter imports now retain a durable receipt key per file, so explicit retry is also safe after a lost response, timeout or transient server failure. See [IMPORT_RECOVERY.md](IMPORT_RECOVERY.md) for scope, batch recovery and restart checks. Successful files are retained, and a failed portal notification never re-uploads them. Save failures keep the editor and unsaved state available for an explicit retry.

The matter/document layout and double-click/right-click interaction model are unchanged. Recovery uses the existing dialogs and editor error surface.

The suite also verifies cross-user document access, audited denials, edit-session
ownership, revocation of issued WebDAV sessions and real session-expiry recovery.
See [ACCESS_AND_SESSION_RECOVERY.md](ACCESS_AND_SESSION_RECOVERY.md) for the
permission policy, audit scope and pinned ONLYOFFICE startup readiness gate.

Responsive column checks cover saved menu proportions, sidebar/viewport changes
without preference writes, divider dragging and reload, minimum widths, and
header/body alignment in matter document lists. See [COLUMN_SIZING.md](COLUMN_SIZING.md).
