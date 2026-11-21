# Invoice allocation integrity

Allocations now require an active payment approver with access to both the invoice matter and every source posting matter. The posting must belong to the invoice matter, including for administrators. Firm-wide accounts visibility is unchanged.

Eligible sources are approved, non-anticipated single client/office credits or balanced client-debit/office-credit bill-payment pairs. Debits, invoice charges/reversals and malformed pairs are rejected. A pair's credit value is counted once. Allocations cannot exceed either the invoice balance or the amount still unallocated from that pair across all invoices. This does not trace funds between separate posting pairs.

Invoice and posting advisory locks serialize checks and writes on PostgreSQL, with conflicts returning HTTP 409 for a user retry. Allocation, cached invoice total, paid timestamp and audit event commit together. An allocated invoice cannot be voided; correction/unallocation needs a separate reviewed workflow. Existing inconsistent totals return 409 and require investigation rather than automatic repair.

The allocation dialog sends an optional UUID `idempotency_key`, retaining it while the same submission is retried after a network error. Reusing that key returns the original allocation; changing its amount, source, notes or actor returns 409. Access is rechecked before replay. Changing the dialog's payload or opening a new dialog starts a new request. Legacy clients without a key remain supported but cannot identify an exact retry; they should adopt request keys. There is no automatic retry of writes.

The migration adds a nullable request key, invoice/request uniqueness and a positive-value check. The PostgreSQL check is initially NOT VALID so historical invalid rows do not block deployment; it still rejects invalid new writes. No financial records are rewritten. Investigate historical records separately before validating that constraint, and do not infer that old allocations have been audited or corrected by this release.

Validation:

- Backend tests cover matter permissions, eligibility, over-allocation, inconsistent totals, revoked access on replay, failed audit/commit rollback and paid timestamps.
- `scripts/test-core-workflows.sh` runs real PostgreSQL competition for invoice/source locks, void races, rollback/retry, migration constraints, and a browser allocation whose successful response is deliberately lost.
- The browser must retain entered details, reuse its request ID, and finish with exactly one allocation and a Paid invoice. Layout, double-click and right-click controls are unchanged.
