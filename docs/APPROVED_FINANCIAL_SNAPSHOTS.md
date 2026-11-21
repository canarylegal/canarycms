# Approved financial report snapshots

Firm-wide client-account and bank reconciliation approvals now save an immutable archive in the same database transaction as approval. Rendering, archive insertion or audit failure rolls back the approval. The current screens, report download, column preferences and double-click/right-click interactions are unchanged.

## What is retained

Each approval version contains:

- The exact existing firm reconciliation DOCX, or a bank reconciliation HTML summary.
- `data.json`: approved ledger source rows at the inclusive UTC cutoff, frozen matter/client/fee-earner labels, reconciliation totals, preparer/approver labels and relevant firm/bank settings. Bank archives also include statement rows through the cutoff.
- `manifest.json`: source and version IDs, cutoff and filters, approval actor/time, capture time, build and renderer version, per-file SHA-256 hashes and sizes, and the preceding archive's ID/hash. Reapprovals include the reopening audit ID and reason.

Bytes are stored in `financial_report_snapshot`, not a separate filesystem directory. Normal database backups therefore retain the archive atomically with its financial data. PostgreSQL triggers reject updates, deletes and truncation. Versions are append-only, and the migration intentionally refuses destructive downgrade.

Existing approvals are **not backfilled**: their original rendered bytes and labels cannot be reconstructed reliably. Their existing DOCX downloads remain available with `X-Canary-Archive-State: legacy-unarchived`. A reviewed reopening and reapproval creates the first archive; do not reopen historical periods merely to populate archives. Draft downloads remain marked `draft`. Ad-hoc reports without an approval workflow remain live reports.

## Access and version history

Authenticated accounts-workspace users can call:

- `GET /reports/approved-snapshots?source_kind=firm|bank&source_id=<UUID>&limit=25`
- Continue with `before_version=<next_before_version>` for older versions.
- `GET /reports/approved-snapshots/<snapshot UUID>/download` for the ZIP bundle.

These are backend paths; through the web application prefix them with `/api`. Full archives and their history require access to every referenced matter because the supporting data contains matter details. The existing firm summary DOCX and accountant-pack summary require accounts permission but do not expose the supporting rows.

The existing firm report download and accountant export pack reuse the exact archived DOCX. A reopened draft never overwrites older versions. Every successful archive download commits a `financial.snapshot.download` audit event (actor, artifact and SHA-256) before returning bytes. Draft/legacy report and other accountant-pack downloads use `financial.report.download`. Access denials use the existing `access.denied` audit mechanism. Direct archive integrity failures log `financial.snapshot.integrity_failure` without releasing bytes.

## Verification and recovery

Run against a selected backend deployment:

```sh
python scripts/check_financial_snapshots.py
```

This command uses a read-only repeatable-read transaction, verifies every artifact and version link, and checks current archived approvals against their approval timestamp. It prints hashes and explicitly lists legacy approvals. Exit 0 means verification completed (legacy approvals may remain); exit 3 means verification failed. It neither repairs nor backfills anything. No scheduled job is installed or enabled.

For recovery, follow `docs/DISASTER_RECOVERY.md` to restore the database and files into an isolated deployment. Run the checker there and compare archive hashes with the pre-restore output. Verify the selected archived download and its audit event before any approved recovery cutover. If corruption is found, retain the damaged database for investigation and recover from a verified backup; never regenerate an approved archive silently. Failed verification returns HTTP 409 rather than a replacement report.

The core workflow suite exercises real PostgreSQL update/delete/truncate rejection, competing approvals, rollback after rendering failure, authenticated downloads and access denial. It dumps the isolated database, restores into a second database, compares all archive hashes and verifies the restored mutation trigger before cleaning up.

## Operational limits

Each approval currently has a 64 MiB uncompressed artifact limit; an oversized archive aborts approval. Archives retain supporting rows for each approval, so database size and backup duration will grow with reporting history. The build commit may be `unknown` in non-release test environments.

The hashes and database triggers detect corruption and prevent ordinary application edits. They are not externally signed evidence or tamper-proof storage against a privileged database administrator who can disable triggers and rewrite all hashes. Independent backup retention or externally anchored signatures are separate controls.
