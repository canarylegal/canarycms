# Matter import recovery

The matter Import button and drag/drop retain their layout and interactions. Each selected file gets a UUID `Idempotency-Key`, retained with batch progress while the retry dialog is open. A lost response, timeout or transient server failure offers **Retry** through that existing dialog. Uploads are never replayed automatically. Acknowledged files are skipped; the uncertain file keeps its key, then the remaining files continue.

A 400/413/422 rejection identifies an individual invalid file. The batch proceeds with other files and reports accepted counts plus rejected filenames/reasons in the existing action error area. Permission failures or an invalid destination stop the batch; session expiry offers sign-in recovery. Changing matter/folder or unmounting stops further batch requests. Portal notifications include only accepted files and do not re-upload documents if notification fails.

## Server contract

`POST /cases/{case_id}/files` accepts an optional UUID `Idempotency-Key` header. Existing clients without it retain the previous behavior. Receipt IDs are scoped to the authenticated user and matter. Access is checked before every replay. A fingerprint covers original bytes, filename, content type, destination, parent and all upload options. Reusing a key with different content/options returns 409; it never overwrites an earlier upload. Concurrent attempts are serialized with a PostgreSQL transaction advisory lock; a busy receipt returns 429 for explicit retry.

The receipt and document/audit/outbox records commit in the same transaction. A replay returns the original response with status 201 and does not repeat the upload event or post-commit notification attempt. Receipts survive backend restarts and document deletion: a replay of a deleted file returns 410 rather than resurrecting it. Receipts are small, persistent records; this release does not schedule their removal.

The stored file ID is stable for a keyed attempt. Interrupted writes remove their `.partial` file where an exception can be handled. Known transaction failures remove uncommitted bytes. A lost COMMIT acknowledgement is checked before cleanup so committed bytes are not accidentally deleted. If the database is unreachable and the outcome cannot be established, bytes are retained; retrying the same key recovers the operation instead of creating a second file. An abrupt process kill can leave unreferenced bytes/partial files until that attempt is retried; this is not a general orphan-file sweeper.

Retry state is held in the open browser window, not persisted across reload/close or Cancel. Retry from that dialog to reconcile an uncertain result. Starting a new import intentionally creates new keys and may create another copy of the same content. This release does not add resumable byte-range transfers, a job queue, or automatic retries for other clients. Portal e-mail delivery is separate from durable document acceptance and is not guaranteed exactly once.

## Isolated validation

`make test-core-workflows` uses a fresh guarded test database, file volume and service project. It now includes:

- PostgreSQL contention on one receipt with explicit retry, checking one stored document.
- A committed upload whose HTTP response is discarded, followed by browser retry using the same key.
- Batch continuation after a rejected individual file and a 32-file import interrupted midway.
- Concurrent duplicate requests, a 16 MiB attachment replay, changed-payload rejection and denied-user access.
- An upload/replay in separate Python processes on opposite sides of a real backend restart; file bytes and the single audit event must match.

Backend unit tests inject storage, stream, lifecycle/outbox and commit failures, including a commit that succeeds before its acknowledgement is lost. They also cover deleted documents, user scopes, revoked access, changed options/content, size limits and attachment linkage. Frontend tests verify stable keys, acknowledged-file skipping, rejected-file reporting, session recovery and no automatic POST retries.

The migration adds only `upload_receipt`; no existing database rows or file bytes are rewritten. Live deployments and scheduled jobs are not touched by these tests.

## Durable publication and receipt integrity

Staff and portal upload helpers flush file data and containing directories before
publishing database records. New file records retain a SHA-256 of the final stored
bytes, including converted mail. Temporary upload names are unique per attempt.
A flush failure prevents database publication; an uncertain commit retains bytes.

Matter-upload receipt replay checks the current locked File row, readable storage
and its recorded checksum. Missing, corrupt or unverifiable content returns 409
for recovery rather than confirming success. Legitimate subsequent document
versions remain valid when their current bytes match their current checksum.
Deleted documents still return 410. Historical rows without checksums are not
silently trusted or backfilled; their retries require explicit integrity review.

## Precedent uploads

`POST /precedents` accepts an optional UUID `Idempotency-Key`. The receipt is scoped
to the administrator and fingerprints the file bytes, filename, MIME, name,
reference, kind and matter/category scope. The admin upload form retains its key
while the same form/file is retried after an uncertain response; it resets after
confirmation or changed input. Keep the form open and unchanged to retry. Keys
are not retained across page reloads; after losing the form, check the library
reference before starting another upload.

The precedent, File, audit and receipt commit together. An identical retry returns
the original result without another file; changed input returns 409, a concurrent
attempt 429, a deleted precedent 410, and missing/corrupt bytes 409. Reference
validation occurs before file allocation and reference claims serialize in
PostgreSQL. Clients without a retry key remain supported; duplicate references
are rejected before writing. The shared `CANARY_UPLOAD_MAX_BYTES` limit also
applies to precedents, including DOCX validation input (default 25 MiB).

These changes reuse the existing receipt/checksum schema. They do not backfill
firm records, enable jobs or introduce automatic orphan cleanup.
