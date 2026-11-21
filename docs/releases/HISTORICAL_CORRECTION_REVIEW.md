# Historical financial review and controlled corrections

This operator release adds evidence investigation and a narrowly scoped correction:
removing a statement match whose referenced posting no longer exists. It adds no
HTTP endpoint, UI change, migration or scheduled job. Deploying it applies no repairs.

## Review first

Run on an isolated restored backup first. Keep output private (`umask 077`): it contains
record UUIDs, dates and amounts, though no client names, descriptions or raw audit metadata.

```sh
docker exec canary-backend python scripts/historical_financial_review.py investigate > investigation.json
docker exec canary-backend python scripts/historical_financial_review.py preview-unmatch \
  --line-id STATEMENT_UUID > proposal.json
```

Both commands use a PostgreSQL repeatable-read, read-only snapshot and rollback. They
print JSON only after completing successfully. Exit 0 means the command completed,
**not** that the data is correct or a proposal is unblocked. Exit 3 means failure;
stdout contains no partial success report. Inspect `summary`, `blockers` and evidence.
These are operator scans that load historical records, not interactive endpoints.

Investigation associates recognition gaps with ledger fingerprints, direct audit events,
UUID references in retained audit metadata, and invoice approval/void links. Compare
those records between independently restored backups, preserving each source checksum
and schema/migration provenance. Reference matches are evidence for review, not proof
of an approval date. Absence of evidence is not proof of a financial error. No tool
backfills approval dates, recreates postings or guesses replacement matches.

## Reviewed unmatching

A proposal states the exact before/after values, current version, source-content hash,
bank/date/amount, missing posting check and approved-period blockers. Its SHA-256 hash
binds the review to that complete proposal. It is a stale-evidence check, **not a digital
signature or authentication credential**. The security boundary is trusted host/database
access; the operator supplies an active administrator's identity for attribution and
must obtain separate review approval before invoking apply. Do not expose this CLI
through an unauthenticated web service.

An approved reconciliation blocks execution. Use the existing reasoned reopen workflow
only after approval, then generate and review a **new** proposal. The tool never reopens
periods automatically and never updates saved reconciliation totals silently.

After separate approval, copy the reviewed JSON to a private path in the backend and run:

```sh
docker exec canary-backend python scripts/historical_financial_review.py apply-unmatch \
  --plan /private/proposal.json --actor-id ADMIN_UUID \
  --reason 'Approved review reference and specific correction rationale' \
  --approve-plan-hash EXACT_REVIEWED_HASH
```

The command requires an active administrator and a bounded, nonempty reason. It takes
the existing bank/pair locks, locks the statement row, rechecks all preview evidence,
checks the period, and calls the existing versioned unmatch service. Any posting now
present, changed statement or changed approved-period set requires a new review.
Only the statement match changes; ledger amounts and recognition dates do not.
The statement becomes unmatched, which changes reconciliation presentation and may
require refreshed totals and reapproval through the normal workflow.

The statement mutation, normal bank audit event and correction receipt commit together.
Success is printed only after commit. Audit or commit failures cannot report success.
Retry exactly the same plan/hash after an uncertain response: a durable receipt returns
`already_applied`, without changing the line again, even if later work altered it.
A busy-bank conflict returns exit 3 / code 409: retry after the competing transaction
finishes; stale evidence requires a fresh preview. Check receipt status rather than
assuming every failure means no commit occurred (a connection can fail after commit).

## Recovery and limits

The normal statement history retains before/after match state, and the correction receipt
retains the reason and full proposal state. The existing reasoned restore workflow still
validates the target posting and period; it intentionally cannot restore a dangling match.
If unmatching was the wrong decision, review the preserved evidence, establish a valid
posting and use the standard matching workflow. Do not recreate a missing financial
posting solely to make a reference valid, or edit/delete audit receipts.

No correction plan authorizes changes by itself. Keep proposals, approvals and receipts
together. This release's real-data rehearsal runs only in a disposable clone; dev retains
its original historical findings pending review. Do not enable scheduled jobs as part of
this release.

## Verification

Tests cover read-only deterministic previews; hidden source changes; changed amounts,
versions and postings; closed periods; malformed approvals; inactive/non-admin actors;
atomic rollback on audit failure; no success on commit failure; duplicate retries; later
edits after a receipt; retained metadata references; and real PostgreSQL races against
corrections, ordinary unmatching, rollback and reconciliation approval. No real client
records are included in committed test fixtures.
