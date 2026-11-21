# Canary Sign concurrency and recovery

Signing, cancellation, decline, shared-form ownership/edits and viewed-state updates now serialize on the signing request. State and recipient membership are refreshed after acquiring the lock. Completion requires an active, unexpired request with at least one recipient and all recipients signed.

A repeated signature submission with the same persisted field values returns the existing result without duplicating signatures, audits or artifacts. A different payload returns a conflict. For a historical pending request whose recipients are already signed, the same submission can retry finalisation. This does not reopen cancelled, declined or expired requests, and no historical records are rewritten automatically.

Snapshot and artifact reads verify their stored SHA-256 checksum. A checksum mismatch returns an integrity error; a corrupt signed document is not silently replaced by its unsigned preview. Legacy files without a stored checksum remain downloadable and emit an explicit diagnostic warning; they are not claimed to be verified, and no baseline is silently created. Establishing a baseline for those files requires a separately reviewed provenance/backup comparison. Recover mismatching files from a verified backup, then retry. Do not change the checksum to legitimise unexpected bytes. File recovery should be reviewed and recorded by an operator.

Failures before the database commit roll back signature state; immutable unpublished artifact candidates remain available to existing document-recovery tooling. Do not delete files based solely on a failed request. After an ambiguous response, replay the original signature payload; do not submit a changed signature as a retry.

## Verification

`backend/tests/test_canary_sign_postgres.py` runs in the disposable PostgreSQL stage of `scripts/test-core-workflows.sh`. It exercises real PDF generation, concurrent final signers and duplicate submissions, shared-form claims, cancellation/decline races, stale view state, replay conflicts, historical stranded completion, corrupt/missing files and generation/notification/commit failures. The normal unit suite skips these database integration tests when PostgreSQL is unavailable.

The disposable core workflow stack explicitly disables background jobs. This release changes no frontend layout or interactions and no DocuSign integration. Deployment must retain existing database/files volumes and keep `CANARY_BACKGROUND_JOBS_ENABLED=0` and scheduled timers disabled.
