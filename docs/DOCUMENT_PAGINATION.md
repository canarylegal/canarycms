# Progressive matter documents

The main document browser uses `GET /cases/{case_id}/files/browse` for at most 100 documents per request, loading more on scroll or Arrow Down at the loaded boundary. Existing document controls, column widths, double-click opening and context menus are retained. The legacy file-list API remains available for integrations and the portal document picker.

The browse endpoint accepts `folder`, `q`, `sort=description|size|created|user`, `direction=asc|desc`, `limit=1..100` and a query-bound `cursor`. Every request checks current matter access, including continuation requests. Hidden compose drafts and system folder markers are excluded from document rows.

Pinned parent groups come first; regular groups follow. Each parent precedes its immediate attachments, with attachments sorted within that group. The keyset includes parent and child sort values, creation timestamps and IDs. A group larger than one page continues on the next page without skipping or interleaving another group, and without returning an unbounded attachment array. Folder rows retain their existing position between pinned and regular groups.

Search is the existing trimmed, case-insensitive literal substring search over filename, sender name and sender address. A match includes related parents, siblings and descendants before applying the current-folder filter. The recursive SQL closure is scoped to the matter and uses UNION to terminate even for cyclic legacy links. Rendering retains the existing immediate-parent hierarchy; it does not introduce a new nested-document UI.

`GET /files/folder-metadata` (under the same matter prefix) independently supplies all folder paths and summaries. Counts reflect the complete dataset, not loaded pages. Empty folders represented by system markers remain visible. This small hierarchy response is not paginated; its size grows with the number of distinct folders. The new file index supports case/folder/visibility lookups using a fixed-size MD5 path key plus an exact path predicate, so long paths cannot exceed the B-tree entry limit and hash collisions cannot mix folders. Joined text sorting and recursive search can still scan matching records; this is not a claim of constant-time database work. Optional commercial enrichment retains its provider's existing case-level API.

Text uses PostgreSQL ICU root collation, consistent across clients. Date ordering uses the stored e-mail date for root mail documents and creation time otherwise; size is numeric. The deployment's pinned PostgreSQL image provides ICU support.

Query changes cancel requests; old responses cannot contaminate a new folder/matter. Page failures retain already loaded rows and stop automatic retries; use the existing Refresh control to restart. Uploads, deletes, moves, saves and cross-tab changes invalidate the list and folder metadata. Refresh starts at the first page. Selection survives additional pages and shift-range selection includes loaded rows; changing folder/search or refreshing clears stale selection. No column preferences are written by pagination. A direct protected metadata lookup lets integration-result links open a document that has not yet been loaded.

Cursors are positions, not snapshots or access tokens. Insertions/deletions before the cursor do not shift continuation. Concurrent edits that move a document's sort/group/filter values can move it across a boundary; the client deduplicates IDs, and Refresh reloads current results.

## Verification

`make test-performance` runs migrated PostgreSQL tests for large attachment groups, every sort/direction, literal searches, cross-folder matching, empty folders and inserts/deletions at page boundaries. API/browser workloads compare all 1,200 synthetic documents with the legacy response and enforce bounded rows, payloads and query counts. `make test-core-workflows` covers access revocation, failure recovery, document editing/saving, uploads, session recovery and saved columns. Frontend unit tests cover races, cancellation, retries, selection and keyboard continuation.

All tests use disposable deployments. Merge/deployment and scheduled-job activation are separate actions.
