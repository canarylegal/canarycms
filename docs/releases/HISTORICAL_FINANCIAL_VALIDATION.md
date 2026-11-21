# Historical financial-data validation

This release adds an operator-only diagnostic command. It does not change the UI,
create schedules, expose a new HTTP endpoint, or repair any financial records.

## Run and review

From the deployment host, using the existing backend container:

```sh
umask 077
result=0
docker exec canary-backend python scripts/check_financial_data.py > financial-review.json || result=$?
# 0 = clear; 1 = inconsistencies; 2 = evidence gaps only; 3 = execution failed.
```

Check the exit status before reading the report. A nonzero status is deliberately
expected when records need review. Exit 3 produces no partial JSON report on stdout;
stderr contains only a failure category. Keep reports private: they contain UUIDs
and amounts, though no client names, descriptions, account numbers or raw audit data.

The command starts PostgreSQL REPEATABLE READ, READ ONLY before querying. It takes
no application/advisory locks, writes no audit rows, and rolls back its transaction.
It loads financial records in memory, and reuses invoice allocation validation per
invoice; run it as an operator task against an isolated restored backup first for
large datasets. It is not a background job or a web request.

## Checks and priorities

1. **Errors:** invoice line totals and charge/void links; allocation caches, capacity,
   paid state and cross-matter sources; posting amounts, shapes and approval state;
   negative client balances (including bank buckets); transfer legs and compensating
   reversals; missing operation results; invalid bank matches; saved reconciliation
   arithmetic; orphan links and impossible event ordering.
2. **Review items:** missing approval/void evidence, approval times recoverable from
   audits but absent from the ledger, historical corrected cross-matter
   allocations, and statement import count differences. These require investigation;
   they do not establish that money is missing or that a timestamp should be invented.

A single-leg client or office posting is valid in Canary. Do not apply a blanket
"every pair must have two legs" rule. Missing recognition timestamps are distinguished
from affirmative approval evidence in retained ledger audit records. Recognition
coverage is counted by posting pair, not ledger leg. Audit evidence is never written
back automatically.

The reconciliation bridge explains these current-state identities in integer pence:

- Office balance = invoice-linked office postings + other office postings.
- Outstanding invoice principal = approved invoice totals − their active allocations.
- Draft billing is shown separately; it is not posted debt or cash.

These are different accounting measures. A positive office balance and outstanding
invoices can legitimately coexist. The bridge is descriptive, not an independent
certification: examine invoice/posting findings before relying on it. Stored approved
reconciliations are checked against their own arithmetic, not today's balances;
later postings or matching corrections must not be misreported as corrupt snapshots.

## Isolated restore procedure

Use `scripts/recovery_drill.py` and a verified paired database/files backup. It creates
unique `canaryrestore-*` volumes, an internal-only network and no host ports. Do not
mount live volumes. Keep background jobs disabled and use the backup's matching
optional package and encryption key through the private restore configuration.

The first boot intentionally does not migrate. If the backup predates the tested
code's schema, explicitly run its migrations only in the isolated clone. Record that
schema conversion separately; then fingerprint all financial columns before and after
the diagnostic. Verify the restored files against the backup manifest and run
`backend/scripts/verify_recovery_readonly.py` for authenticated matter/document checks.
Destroy only the clone's project and volumes when finished. Keep the original backup
and private diagnostic evidence for review.

## Corrections remain a separate step

The report includes stable codes, affected UUIDs and evidence, but no executable fixes.
For a flagged match, inspect the statement, linked posting and audit history. A missing
posting does not prove which replacement posting (if any) is correct. If the period is
approved, use the existing reasoned reopen/correction workflow after review. Never
silently detach a match, recreate a posting, rewrite a cache or invent an approval date.

This is a bounded current-state validator, not a forensic event store: it cannot prove
all historical permissions, reconstruct deleted history, validate unseen bank statements,
or infer the correct intended accounting entry. Findings may overlap when one damaged
record violates several invariants. Review the underlying records before prioritising
repairs; preserve original evidence and require separate approval for corrections.

## Regression coverage

Synthetic versions of restored-data findings, valid cash/debt differences, damaged
invoice/ledger/transfer links, reversal chronology, saved snapshot arithmetic, deterministic
SELECT-only execution, explicit CLI failures, and real PostgreSQL read-only snapshot
behaviour under concurrent changes. No real client data is committed as test fixtures.
