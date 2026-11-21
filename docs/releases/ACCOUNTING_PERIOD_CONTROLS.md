# Accounting period controls

Approved firm-wide client-account reconciliations now close their inclusive UTC period
for financial events across the firm. Existing approved bank reconciliations continue
to close statement changes and client postings on their own bank. No schema migration,
UI change, schedule, automatic reopening or historical correction is included.

## Write coverage

- Actual client and office postings, including legacy untagged client accounts.
- Pending/anticipated posting recognition and invoice approvals.
- Invoice creation and void events, allocations and allocation reversals.
- Both sides of inter-matter transfers and their compensating reversals.
- Bank imports and match/ignore/restore corrections, using the statement date.

Each event is checked at the same UTC timestamp it records. Transfers share one instant
across both legs. Invoice and charge/reversal recognition remain aligned. A legacy
pending invoice whose charge was already approved cannot be backfilled into a closed
firm period. Successful idempotent retries return existing receipts without reposting,
even after closure. New work receives HTTP 409 when its effective date is closed.

Later corrections are new dated events. Correcting an old item today need not reopen
its original period if today's period is open and the change preserves the original
history. Matching changes affect the historical statement date, so that date must be
open. Pending ledger estimates are working data, not recognised balances; their later
approval is checked at recognition. This does not freeze client names, fee-earner
assignments or other mutable report labels, and is not a tamper-proof financial archive.

## Concurrency and permissions

Financial writes take a shared transaction-scoped accounting lock. Firm-wide snapshot
creation/update/approval/reopening takes its exclusive counterpart. A close cannot
approve totals while a financial write is uncommitted, and a write cannot cross a close.
Shared locks allow ordinary writes to different matters to proceed concurrently; existing
matter, bank, invoice and request locks still protect their own invariants. Conflicts
return 409 rather than waiting indefinitely; rollback and retry the entire operation.

Firm-wide snapshot create/update requires the accounts workspace. Approval and reopening
require an active approver. The controls cover application services, not direct SQL by a
database administrator, restoration, or an external package bypassing those services.
Review existing approved cutoff dates before deployment, especially future-dated approvals.

## Explicit reopening without changing the UI

Bank reconciliation reopening uses the existing versioned, permission-checked workflow.
Its audit now includes the affected bank/report scope and remaining approved barriers.
Reopening does not refresh or approve totals automatically.

Firm-wide reopening is an operator CLI, leaving the current interface unchanged:

```sh
umask 077
docker exec canary-backend python scripts/accounting_period_review.py preview \
  --reconciliation-id RECONCILIATION_UUID > period-review.json
```

The preview uses a PostgreSQL repeatable-read, read-only transaction. It contains the
financial snapshot, a notes fingerprint, affected report categories and all remaining
approved barriers. Keep it private. After reviewing that exact preview and obtaining
separate approval for the specific reopening:

```sh
docker exec canary-backend python scripts/accounting_period_review.py reopen \
  --reconciliation-id RECONCILIATION_UUID --actor-id APPROVER_UUID \
  --reviewed-hash EXACT_PREVIEW_HASH --reason 'Review reference and correction rationale'
```

Trusted host/database access is the operator security boundary. A hash detects stale
review evidence; it is not an authentication credential or digital signature. The actor
must still be an active approver. Changed snapshot, notes or remaining-approval scope
requires a fresh preview. The command atomically records the financial before-state,
notes hash, actor, reason, review scope and transition to draft. Original snapshot totals
and notes remain intact. Approval fields are cleared and normal reapproval refreshes totals.
Earlier or later approved rows continue to protect their respective dates; reopening one
row does not cascade through other rows or banks.

Exact reviewed-hash retries return `already_reopened`, even if subsequent work reapproved
the period; they never reopen it again. Success is printed only after commit. Exit 3
means failure and produces no success JSON. A lost connection may still follow a commit:
retry the same reviewed hash to resolve that ambiguity. Exit 0 means the command completed,
not that a preview is approved or free of blockers.

## Historical stability and deployment checks

Regression tests compare earlier aged debt, billing, balances, ledger activity and
reconciliation totals after later approvals, voids, allocation corrections, transfers
and reversals. Boundary tests cover the last instant of a closed UTC day and the first
instant of the next day. Failure tests cover denied/stale reopenings and audit/commit
failures. Real PostgreSQL tests race period transitions against office postings,
allocations, allocation reversals and transfers, including transaction rollback.

An equal-timestamp invoice fixture exposed a related response bug: creating an invoice
selected the first row by date instead of the new invoice ID. Creation now returns the
exact new invoice, with a regression assertion; no layout or interaction changes.

Before deployment, capture financial/file/preference fingerprints and inspect approved
cutoffs read-only. After deployment, compare fingerprints, run health/browser checks and
read-only diagnostics. Do not reopen a deployed historical period as a smoke test.
Keep scheduled backup and monitoring jobs disabled.
