# Invoice allocation integrity

Allocations now require an active payment approver with access to both the invoice matter and every source posting matter. The posting must belong to the invoice matter, including for administrators. Firm-wide accounts visibility is unchanged.

Eligible sources are approved, non-anticipated single client/office credits or balanced client-debit/office-credit bill-payment pairs. Debits, invoice charges/reversals and malformed pairs are rejected. A pair's credit value is counted once. Allocations cannot exceed either the invoice balance or the amount still unallocated from that pair across all invoices. This does not trace funds between separate posting pairs.

Invoice and posting advisory locks serialize checks and writes on PostgreSQL, with conflicts returning HTTP 409 for a user retry. Allocation, cached invoice total, paid timestamp and audit event commit together. An invoice with active allocations cannot be voided; reverse incorrect allocations through the audited correction endpoint before correcting its receipt or invoice. Existing inconsistent totals return 409 and require investigation rather than automatic repair.

The allocation dialog sends an optional UUID `idempotency_key`, retaining it while the same submission is retried after a network error. Reusing that key returns the original allocation; changing its amount, source, notes or actor returns 409. Access is rechecked before replay. Changing the dialog's payload or opening a new dialog starts a new request. Legacy clients without a key remain supported but cannot identify an exact retry; they should adopt request keys. There is no automatic retry of writes.

The migration adds a nullable request key, invoice/request uniqueness and a positive-value check. The PostgreSQL check is initially NOT VALID so historical invalid rows do not block deployment; it still rejects invalid new writes. No financial records are rewritten. Investigate historical records separately before validating that constraint, and do not infer that old allocations have been audited or corrected by this release.

Validation:

- Backend tests cover matter permissions, eligibility, over-allocation, inconsistent totals, revoked access on replay, failed audit/commit rollback and paid timestamps.
- `scripts/test-core-workflows.sh` runs real PostgreSQL competition for invoice/source locks, void races, rollback/retry, migration constraints, and a browser allocation whose successful response is deliberately lost.
- The browser must retain entered details, reuse its request ID, and finish with exactly one allocation and a Paid invoice. Layout, double-click and right-click controls are unchanged.

## Audited allocation corrections

The existing allocation dialog, layout and interactions are unchanged. Authenticated support clients can call `POST /cases/{case_id}/invoices/{invoice_id}/allocations/{allocation_id}/reverse` with a UUID `idempotency_key` and a nonblank `reason` (up to 2,000 characters). Payment-approval permission and access to the invoice and source matters are required, including on a retry. An allocation must belong to the invoice in the URL.

A correction reverses the entire allocation; it does not delete or edit the original row or move ledger money. The reversal row, reduced invoice total, cleared paid timestamp and reasoned audit commit together. To correct a partial amount, reverse the old allocation then allocate the intended amount using the existing dialog and a new request key. These are two explicit operations: if reallocation fails, the invoice remains correctly unallocated and its receipt capacity remains available. Other invoices can legitimately use that capacity in the meantime.

Reusing the same correction key and details returns the same reversal, including after later reallocation, receipt reversal or invoice voiding. Changed details with the same key, or a second key for an already reversed allocation, return 409. Database uniqueness and transaction locks protect simultaneous corrections and races with allocations, ledger reversal and invoice voiding. Retrying the original allocation request returns its original row with reversal metadata; it never reapplies it. Keep request IDs across ambiguous responses and restarts.

Allocation list/create responses now include `reversal` (null for active allocations, otherwise ID, actor, reason and timestamp). Historical rows remain in the list. Consumers must not sum all historical allocation amounts: only rows with no reversal count toward payment or receipt capacity. Removing an allocation does not itself undo a bank match; the separate bank and ledger correction safeguards still apply.

## Consistency checks

`GET /cases/{case_id}/invoices/{invoice_id}/allocation-consistency` returns a read-only report for an authorised payment approver. It checks active allocation totals against the invoice cache, paid status, invoice and receipt capacity, eligible postings, cross-matter sources and allocations on non-approved invoices. Locks prevent a concurrent correction being mistaken for inconsistency; a busy operation can return 409 and be retried.

For an operator-led audit of the whole deployment, run `python scripts/check_invoice_allocations.py` inside the backend container. It uses a single PostgreSQL repeatable-read, read-only snapshot, prints JSON findings and exits 1 for discrepancies (0 when consistent). It does not run on a schedule. Store reports privately. Neither check rewrites historical data or recomputes cached values automatically. Discrepancies block unsafe mutations and require investigation; do not bypass them by editing totals until the underlying records have been reviewed.

Migration `fe9c0d1e2f3a` adds only the reversal table, constraints and uniqueness indexes. It does not mark historical allocations as corrected. Downgrade refuses to discard existing reversals; use a coordinated database/files backup if rollback is required.

Tests cover lost responses, revoked permissions, audit/flush/commit failures, shared-receipt capacity, stale paid flags, historical discrepancies and PostgreSQL races. Browser coverage verifies that a corrected Paid invoice becomes allocatable through the unchanged dialog. A real backend restart must retain the same correction ID and one audit event. Scheduled jobs remain disabled.
