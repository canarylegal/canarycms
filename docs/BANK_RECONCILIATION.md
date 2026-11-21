# Bank reconciliation and recoverable matching

The Banking screen retains its layout and Match/Unmatch interactions. Its writes now include the displayed record version. Old browser tabs should reload after deployment. A competing edit returns 409; refresh and review the current state before submitting another correction. A lost match/unmatch response refreshes the screen without automatically repeating the write.

## Financial rules

- Bank totals use all approved, non-anticipated client postings tagged to the selected bank, through the inclusive period-end date in UTC. No 500-row display limit applies to calculations or unpresented exports. Untagged legacy postings are not silently assigned to a bank.
- Ledger, unpresented and unmatched amounts are calculated in one SQL statement. A posting matched to a later-dated statement remains unpresented at the earlier cutoff; a statement matched to a later posting remains unmatched at that cutoff.
- Matching requires one approved, non-anticipated client leg, the exact bank and signed amount, and access to every referenced matter. A posting can match only one statement line, enforced both under locks and by a database uniqueness constraint. Split/aggregate matches and internal multi-client-leg journals need a separate workflow; they are rejected here.
- Firm-wide accounts visibility is unchanged. Mutations require an active accounts user; approval/reopening additionally requires payment-approval permission.
- Approval refreshes totals before deciding whether an explanation of a non-zero difference is required. Invalid historical matches stop reconciliation for review; the release does not silently repair them.
- Reports' firm-wide month-end reconciliation also uses the selected cutoff and refreshes at approval. Approved totals are snapshots of the ledger known at approval, not a reconstruction of when an old posting was first approved. Subsequent backdated approvals may change a newly calculated report; they do not rewrite existing approved snapshots.

## Corrections without losing history

Every changed match, unmatch, ignore, unignore and restore records its previous/new state, actor and version in the same transaction. Failed audit or commit means no partial correction is saved. A successful response lost in transit can be resolved by reading the current line/version and history.

The existing Unmatch button releases a match. Match then applies a different eligible posting. Support recovery APIs provide an audited undo without introducing new controls:

1. GET `/accounts/banking/statements/lines/{line_id}/history` returns correction events.
2. POST `/accounts/banking/statements/lines/{line_id}/restore` with `event_id`, the current `expected_version`, and a non-empty `reason` restores the state **before** that event. Eligibility, matter access, duplicate matching and closed-period rules are checked again. Undo cannot take a posting now matched elsewhere.
3. POST `/accounts/banking/statements/lines/{line_id}/ignore?ignored=false` with `expected_version` restores an ignored line to Open. Restoring its former match uses the history operation above.

Approved bank periods block statement imports and corrections dated on or before their cutoff. To correct one, a payment approver POSTs `/accounts/banking/reconciliations/{id}/reopen` with current `expected_version` and `reason`. The old approved financial snapshot stays in the audit trail; the row becomes draft. Reopen every affected approved period before correcting older lines, then refresh/update and reapprove each affected reconciliation. PATCH accepts `expected_version`, `statement_balance_pence` and `notes`; approval also requires `expected_version`. Reopening never fabricates a balancing ledger entry or deletes statement history.

These are authenticated APIs (application prefix `/api`), intended for authorised support/operations until dedicated correction controls are requested. They are not public recovery links. Historic corrections made before this release have no new undo event; investigate those records separately.

## Deployment and verification

The migration widens reconciliation totals to 64-bit integers so complete datasets can exceed the former £21.47m aggregate limit, and adds line/reconciliation versions, unique matched-payment identity and a match/ignore state check. Duplicate historical matches stop migration with a review-required error; nothing is deduplicated automatically. The state check is NOT VALID for existing rows, while enforcing new writes.

Run backend tests plus `scripts/test-core-workflows.sh`. The isolated stack checks large period datasets, both sides of date boundaries, permissions, rollback, conflicting matches, approval/correction races, database constraints and browser recovery after a lost response. Dev verification uses synthetic records only. Scheduled jobs remain disabled.
