# Progressive matter menus

The matters and quotes menus now request up to 100 rows at a time from authenticated `GET /cases/menu`. Scrolling near the end loads another page; Arrow Down at the loaded boundary continues into the next page. The existing table, saved widths, column resize controls, filters, sorting, double-click and context menus remain in place. Document lists are unchanged.

Search is a trimmed, case-insensitive **literal substring** of the displayed reference, client, description, status label, active fee-earner label and source. As before, a nonempty search overrides the saved matter-type, fee-earner and status filters, while retaining the matters/quotes split. Clearing search restores those filters. `/cases/menu-options` supplies matter types across the entire firm so pagination does not hide filter choices. Neither request writes preferences.

The menu remains visible firm-wide to authenticated staff. Matter detail, documents and other child routes retain their existing access checks. The old `/cases` API and its existing search behavior remain unchanged for integrations and pickers.

## Ordering and continuation

Parameters: `q`, `menu=main|quotes`, `sort=reference|client|matter|feeEarner|status|source|created`, `direction=asc|desc`, repeated `matter_type`, `fee_earner`, `status`, `limit` (1–100) and `cursor`. Responses contain `items` and `next_cursor` (null at the end). No full-list count is required.

Text uses PostgreSQL ICU root collation, corresponding to the usual browser localeCompare ordering; clients with another locale now share a consistent server order. Ties use creation time descending, then UUID ascending, so page boundaries are deterministic. The pinned PostgreSQL image provides the ICU collation. The migration adds creation, status and fee-earner indexes. Substring search and joined text sorting can still scan matching rows; this release bounds materialization, serialization and network results, not every database operation.

Cursors carry the last sort value, creation time and ID and are bound to the query parameters. They are positions, not authorization tokens. Values remain SQL parameters. Invalid or mismatched cursors return 400. Keyset continuation does not shift because an earlier row was inserted/deleted and works after the boundary row is deleted. It is **not a database snapshot**: edits to a row's sort/filter values during traversal can move that row across a boundary. The client deduplicates returned IDs; Refresh reloads current results from the beginning.

Changing query cancels in-flight requests, resets the list, and debounces the next request by 200 ms. Responses from previous query generations are ignored. A failed continuation retains already loaded rows and stops automatic retries; the existing Refresh button restarts the query. Session errors still go through the shared session-recovery handler. Only opened menus load; an opened menu retains its state while navigating to a matter.

## Verification

- `make test-performance`: migrated PostgreSQL tests exercise all sort directions, tied keys, labels, literal wildcard search, filters, quote separation, cursor validation and deleted boundaries; browser/API tests traverse all 5,002 synthetic matters and enforce page/query/payload budgets.
- `make test-core-workflows`: existing document, access, session-recovery and column tests plus matter-menu access and retry tests.
- Frontend unit tests exercise stale responses, aborts, session changes, deduplication and failure recovery.

Deployment is a separate, explicitly authorised action. These test commands use disposable deployments; they do not change live data or activate scheduled jobs.

On the isolated 5,002-matter fixture, the same-run API profiler measured the legacy full list at 3,966,548 bytes / 199 ms median and the first 100-row page at 79,608 bytes / 14 ms median (8 SQL queries each). The smaller response is approximately 98% less data for initial display, not a claim that fetching the entire dataset is 98% cheaper. Local browser initial display was 675 ms, staff sorting 411 ms and search 371 ms; these are short synthetic measurements, not a production SLA.
