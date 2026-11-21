"""Transaction-safe receipt allocations; caller commits allocation, invoice and audit together."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.invoice_allocation_integrity import active_allocation, allocation_total, require_consistent_totals, receipt_capacity, source_allocation_inconsistent
from app.audit import log_event
from app.deps import require_case_access
from app.models import (CaseInvoice, CaseInvoiceAllocation, LedgerAccount, LedgerEntry, User)
from app.permission_checks import user_may_approve_ledger


def list_allocations(db: Session, invoice_id: uuid.UUID) -> list[CaseInvoiceAllocation]:
    return list(db.scalars(select(CaseInvoiceAllocation)
        .where(CaseInvoiceAllocation.invoice_id == invoice_id)
        .order_by(CaseInvoiceAllocation.allocated_at)))


def allocate_to_invoice(db: Session, *, invoice_id: uuid.UUID, ledger_pair_id: uuid.UUID,
                        amount_pence: int, actor: User, notes: str | None = None,
                        idempotency_key: uuid.UUID | None = None) -> CaseInvoiceAllocation:
    if not actor.is_active or not user_may_approve_ledger(actor, db):
        raise HTTPException(403, "Not permitted to allocate invoice payments")
    if type(amount_pence) is not int or not 0 < amount_pence <= 2147483647:
        raise HTTPException(400, "Allocation must be a positive integer number of pence within the supported range")
    inv = db.get(CaseInvoice, invoice_id)
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    require_case_access(inv.case_id, actor, db)

    # Same nonblocking lock order as invoice approval: invoice, then posting pair.
    # The pair lock serializes capacity checks even across different invoices.
    from app.invoice_service import _try_lock_invoice
    from app.ledger_service import _try_lock_ledger_pair
    _try_lock_invoice(db, invoice_id)
    _try_lock_ledger_pair(db, ledger_pair_id)
    inv = db.scalar(select(CaseInvoice).where(CaseInvoice.id == invoice_id)
                    .with_for_update().execution_options(populate_existing=True))
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    require_case_access(inv.case_id, actor, db)
    legs = list(db.scalars(select(LedgerEntry).where(LedgerEntry.pair_id == ledger_pair_id)
                          .order_by(LedgerEntry.id).with_for_update()
                          .execution_options(populate_existing=True)))
    if not legs:
        raise HTTPException(400, "Receipt posting not found")
    accounts = [db.get(LedgerAccount, leg.account_id) for leg in legs]
    if any(account is None for account in accounts):
        raise HTTPException(409, "Receipt account is missing; review the posting")
    # Check every referenced matter before reporting its financial eligibility.
    for case_id in sorted({account.case_id for account in accounts}):
        require_case_access(case_id, actor, db)
    if any(account.case_id != inv.case_id for account in accounts):
        raise HTTPException(400, "The receipt must belong to the invoice's matter")

    if idempotency_key is not None:
        previous = db.scalar(select(CaseInvoiceAllocation).where(
            CaseInvoiceAllocation.invoice_id == invoice_id,
            CaseInvoiceAllocation.idempotency_key == idempotency_key))
        if previous is not None:
            if (previous.ledger_pair_id != ledger_pair_id or previous.amount_pence != amount_pence
                    or previous.notes != notes or previous.allocated_by_user_id != actor.id):
                raise HTTPException(409, "This allocation request ID was already used for different details")
            return previous

    from app.ledger_integrity import require_external_receipt
    require_external_receipt(db, ledger_pair_id)
    if inv.status != "approved":
        raise HTTPException(400, "Only approved invoices can receive allocations")
    capacity, _ = receipt_capacity(db, ledger_pair_id)
    invalid_previous = db.scalar(select(CaseInvoiceAllocation.id).where(
        CaseInvoiceAllocation.ledger_pair_id == ledger_pair_id, active_allocation(),
        CaseInvoiceAllocation.amount_pence <= 0).limit(1))
    if invalid_previous is not None:
        raise HTTPException(409, "Existing allocations need review before allocating")
    invoice_total = require_consistent_totals(db, inv)
    source_total = allocation_total(db, pair_id=ledger_pair_id)
    if source_allocation_inconsistent(db, ledger_pair_id, capacity, inv.case_id):
        raise HTTPException(409, "Receipt allocation totals are inconsistent; review them before allocating")
    if amount_pence > int(inv.total_pence) - invoice_total:
        raise HTTPException(400, "Allocation exceeds the invoice's remaining balance")
    if amount_pence > capacity - source_total:
        raise HTTPException(400, "Allocation exceeds the receipt's unallocated value")

    now = datetime.now(timezone.utc)
    from app.accounting_periods import require_accounting_open
    require_accounting_open(db, now)
    row = CaseInvoiceAllocation(id=uuid.uuid4(), invoice_id=invoice_id, ledger_pair_id=ledger_pair_id,
        amount_pence=amount_pence, allocated_by_user_id=actor.id, allocated_at=now, notes=notes,
        idempotency_key=idempotency_key)
    db.add(row)
    inv.amount_allocated_pence = invoice_total + amount_pence
    inv.paid_at = now if inv.amount_allocated_pence == inv.total_pence else None
    db.flush()
    log_event(db, actor_user_id=actor.id, action="case.invoice.allocate", entity_type="invoice",
              entity_id=str(inv.id), meta={"case_id":str(inv.case_id), "allocation_id":str(row.id),
                                         "ledger_pair_id":str(ledger_pair_id), "amount_pence":amount_pence})
    return row
