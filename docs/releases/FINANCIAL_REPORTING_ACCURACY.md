# Financial reporting accuracy

Financial cutoffs are inclusive UTC dates, implemented as strictly before midnight
of the following day. Amounts are summed as integer pence; exports convert only
at presentation. No UI layout or interaction changes.

## Historical debt and balances

Aged debt uses invoice approval and void timestamps, original allocation timestamps,
and immutable allocation reversal timestamps. Current cached allocated totals and
paid flags cannot erase earlier debt. Outstanding invoices remain visible even if
another credit makes the matter's office balance positive. Office balance is context,
not a second debt total: it repeats for each invoice on the same matter and must not
be summed across invoice rows.

Balance reports include closed/archived matters: their money still counts. The
accountant pack uses its period end for balances as well as aged debt. Fee-earner
scope still applies. Firm reconciliation totals include all matters, so compare to
an all-fee-earner report only after accounting for any unassigned matters.

Ledger recognition is recorded when a posting becomes approved/non-anticipated.
Posting, delayed approval and compensating reversals all record this timestamp.
Balance, activity and bank reconciliation calculations share this effective date.
Original entry dates are retained in storage. Activity reports present effective
recognition dates for approved entries; pending entries retain their entered date.
Approval after a closed bank period cannot backdate money into that period.

Billing remains an invoice register filtered by creation date (including drafts),
not a cash or recognised-revenue report. Its status and void exclusion now reflect
the requested end date. Consequently its total is not expected to equal aged debt
or the ledger: draft invoices, receipts, allocations and non-invoice postings explain
the differences. Tests independently calculate these amounts rather than asserting
that different accounting measures must be identical.

## Snapshot and exports

Every `/reports/` request starts a PostgreSQL repeatable-read, read-only transaction
before authentication queries. Rows, totals, labels and all accountant-pack sections
therefore share one MVCC snapshot. No global locks or scheduled jobs are introduced.
A later HTTP export intentionally takes a fresh snapshot; it may differ from an older
preview after new activity. JSON/XLSX/pack parity is tested on the same source state.
Denial auditing rolls back the read-only transaction before writing the audit event.

## Historical limitations and deployment

Migration `fea0d1e2f3b4` adds nullable ledger `recognised_at` and recovers known approval
times from ledger approval audits and approved invoices. Where legacy approval evidence
is absent, NULL falls back to the original posting date; the system cannot reconstruct
an unrecorded event. Historical invoices without approval timestamps likewise cannot
be proved approved at a cutoff: historical aged debt returns a review-required conflict
instead of silently omitting them. Current aged debt retains its legacy creation-date
fallback for those invoices. Investigate these
legacy gaps before relying on old period reports; never fabricate dates to make totals fit.

Matter ownership, descriptive labels and fee-earner scope reflect current assignments.
Exception and WIP reports retain their existing current-workflow semantics; this release
does not introduce a full historical event store for time entry edits or matter reassignment.
Saved approved reconciliations remain historical snapshots, not silently recalculated.
Current bank match/ignore corrections can change a regenerated reconciliation; use its
saved approval snapshot and audit trail to establish what was approved previously.

The migration is additive and leaves original monetary values and files intact.
Downgrade refuses to discard recognition history: roll forward. Take the standard
verified database/files backup before deployment. Scheduled jobs stay disabled.

## Regression checks

- UTC approval, allocation, correction and void boundaries, including exactly midnight.
- Full payment after cutoff, stale cached totals, and unrelated matter credits.
- Closed-matter totals versus approved ledger legs and firm reconciliation.
- Delayed approval recognised on approval day, without rewriting entered dates.
- Historical invoice-register status and JSON/XLSX/accountant-pack parity.
- Real PostgreSQL concurrent allocation: existing report snapshot is unchanged;
  next request sees the payment; report transactions reject writes.
