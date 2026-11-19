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
