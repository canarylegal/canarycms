# Ledger posting and inter-matter transfer integrity

This release preserves the posting and Banking forms. It adds transactional request receipts, bank-specific client-funds checks, both-matter access checks and compensating reversals. It does not enable scheduled jobs.

## Posting and retry contract

`POST /cases/{case_id}/ledger/post` and `POST /accounts/banking/journals` accept an optional UUID `idempotency_key`. Current forms retain the same key and payload after a failed response and discard it after success. Older API clients without a key retain their previous behavior; they must not automatically retry an ambiguous write. A newly opened posting dialog is a new operation, so check the ledger before re-entering a transaction after closing an uncertain submission.

Keys are scoped to the actor across operation types. The same key and payload returns the originally accepted result without another posting or audit. Changed details with the same key return 409. Access and posting rights are checked again before replay. Receipts survive restarts and subsequent corrections: replay confirms original acceptance, not the current balance, and never recreates a rejected or reversed posting. Refresh the ledger to see current status.

Posting, both transfer legs, operation receipt and audit commit together. PostgreSQL transaction advisory locks serialize shared funds and opposite-direction transfers; contention returns 409 rather than waiting in a deadlock. Retry the unchanged request with the same key. Client debits require sufficient approved actual funds both on the matter and on the original selected bank; untagged historical money is its own bucket. No historical rows are automatically retagged. Posting, approval and reversal also lock the selected bank and refuse to change an approved period covering the current posting date; reopen that period with a reason first.

## Corrections

Authenticated support APIs provide corrections without adding UI controls:

- `POST /cases/{case_id}/ledger/pairs/{pair_id}/reverse`
- `POST /accounts/banking/journals/{journal_id}/reverse`

Both require `{ "idempotency_key": "<new UUID>", "reason": "<correction reason>" }`. Reuse that key to recover a lost response. The response identifies the compensating pair or journal. Original entries remain unchanged; the operation record uniquely links the original to its compensation and the audit records the reason. A new key cannot reverse an original twice, and a compensation cannot itself be reversed. A further legitimate transaction requires a new posting.

A transfer is reversed as a whole, with access and client-post rights on both matters, only while the destination still has the funds. Original bank and contact references are preserved, including archived banks. Individual transfer legs and invoice-owned postings cannot be reversed using the generic posting API. Use invoice voiding for invoice postings. Invoice allocations must be corrected through their workflow first; bank matches must be unmatched through the versioned bank correction workflow (reopening an approved period when required). These dependencies serialize with reversal and block it until resolved. Reversed postings, compensation and internal transfer legs cannot become fresh invoice receipts or external bank matches.

## Validation and deployment

Unit tests inject failure after the first transfer leg and at receipt/audit persistence; they cover access revocation, bank-specific funds, lost responses, spent funds and blocked financial dependencies. Disposable PostgreSQL tests exercise shared funds, first-use accounts, opposite transfers, duplicate requests, rollback, competing reversals and allocation/matching races. Browser tests abort responses after server commit and retry through the unchanged posting/transfer forms.

Migration `fe8b9c0d1e2f` only adds the operation table and indexes; existing financial records are not rewritten. Use the deployment tool's database/files backup before applying it. Do not downgrade after using reversals: removing operation records would lose their retry and reversal guards. Restore a coordinated pre-release backup if rollback is necessary. Keep all scheduled jobs disabled.
