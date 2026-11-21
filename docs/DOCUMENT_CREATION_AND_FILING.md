# Document creation and filing recovery

This release preserves the existing screens, menus, double-click and right-click interactions.

## Guarantees

- File rename, file/attachment moves and folder rename/move change database metadata only. Physical bytes remain at their existing storage path. A failed transaction therefore retains both the original names/filing and readable bytes. Folder metadata and portal grant changes commit together.
- Office/quote compose, completion statements, invoice approval, ONLYOFFICE PDF exports and Canary Sign generated artifacts write fresh candidates under `.created/<file UUID>/<attempt UUID>/`. Bytes and containing directories are synced before publishing the database pointer. Checksums are retained. An uncertain database commit never causes the candidate to be deleted.
- Invoice approval now fails atomically if its document cannot be generated or saved. It does not silently approve without an artifact. A linked invoice document that is missing returns HTTP 409 for recovery rather than silently regenerating potentially different content. Legacy invoices with no linked document retain their existing dynamic download behaviour; this release does not backfill them.
- Signing completion serializes on the request and publishes the signed document, certificate, completion state and audit together. Completion notifications run only after commit; notification failure does not undo committed documents. Notification delivery is not a durable outbox in this release.
- PDF export rechecks matter permissions and the active editing session after the remote fetch, then locks the source before publishing.

## Safe retries

The existing browser requests retain a UUID operation identity across uncertain responses and reloads. After a parsed successful response, a later intentional creation gets a fresh identity. Changed request content gets a different identity. No automatic background retry or scheduled job is introduced.

API callers can supply `X-Document-Operation-ID: <UUID>` for Office/quote compose, completion statements, PDF exports, file rename/move and folder rename/move. Preserve the same identity **and exact request body** after a timeout or lost response. The identity is scoped to actor and matter; receipts and operation results commit in the same transaction. A matching replay returns the original response without repeating changes. Changed content with the same identity returns 409; a concurrent in-flight duplicate returns 429. A deleted created document returns 410 and is never recreated by retry. Permissions are checked again on replay.

Old API callers without this header remain compatible, but do not gain duplicate-creation protection. Invoice approval and signing completion use their existing entity identity/status and locking rather than this header. Generated PDF export URLs are part of the request identity: replay the original request, rather than obtaining a new export URL and treating it as the same operation.

## Partial failures and recovery

A pre-commit failure leaves no published document or successful receipt. Retry the original request to finish it. A commit whose acknowledgement was lost may already have succeeded: the original identity resolves this safely. Never delete candidate files just because a request returned an error.

Read-only inspection:

```sh
python scripts/check_document_creation.py
```

This verifies referenced `.created` files and lists unreferenced candidates for review. Exit 0 means referenced generated documents verified; exit 2 means missing/corrupt referenced bytes; exit 3 means the scan failed. An unreferenced candidate may belong to an in-flight transaction or a rolled-back attempt. It is **not** permission to delete it or reconstruct an approved invoice from it. This scan does not inspect every legacy storage layout and is not a full backup verification.

For a missing/corrupt published artifact, retain evidence and recover the exact bytes from a verified database-and-files backup using `DISASTER_RECOVERY.md`; use retained document versions where available (`DOCUMENT_RECOVERY.md`). Test restoration in isolation before any cutover. No automatic orphan cleanup or historical data correction is performed.

## Verification

Tests inject disk, audit and commit failures, including a commit that succeeds but loses its acknowledgement. They check unchanged source bytes and filing, no duplicate creation on replay, mismatched/deleted retries, invoice approval rollback, signing certificate failure/retry, PostgreSQL concurrent duplicate requests, authenticated browser creation/filing and generated-file integrity across a real backend restart.
