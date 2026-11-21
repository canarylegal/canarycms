"""Transaction-safe receipt allocations; caller commits allocation, invoice and audit together."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.deps import require_case_access
from app.models import (CaseInvoice, CaseInvoiceAllocation, LedgerAccount, LedgerAccountType,
                        LedgerDirection, LedgerEntry, User)
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
    if type(amount_pence) is not int or amount_pence <= 0:
        raise HTTPException(400, "Allocation must be a positive integer number of pence")
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

    if inv.status != "approved":
        raise HTTPException(400, "Only approved invoices can receive allocations")
    # A single client/office receipt, or a balanced client-debit/office-credit bill
    # payment. A transfer to client, two credits, anticipated funds or reversals
    # cannot serve as a receipt. Count a two-leg payment once, never twice.
    kinds = [account.account_type for account in accounts]
    credits = [leg for leg in legs if leg.direction == LedgerDirection.credit]
    valid = (len(legs) in (1, 2) and len(set(kinds)) == len(legs) and len(credits) == 1
             and all(leg.is_approved and not leg.is_anticipated and leg.amount_pence > 0 for leg in legs)
             and len({leg.amount_pence for leg in legs}) == 1)
    if len(legs) == 2:
        valid = valid and all(leg.direction == (LedgerDirection.credit if account.account_type == LedgerAccountType.office
                                              else LedgerDirection.debit)
                              for leg, account in zip(legs, accounts))
    linked_invoice = db.scalar(select(CaseInvoice.id).where(or_(
        CaseInvoice.ledger_pair_id == ledger_pair_id, CaseInvoice.reversal_pair_id == ledger_pair_id)).limit(1))
    if not valid or linked_invoice is not None:
        raise HTTPException(400, "Allocation requires an approved, non-anticipated receipt or bill payment")

    invalid_previous = db.scalar(select(CaseInvoiceAllocation.id).where(
        or_(CaseInvoiceAllocation.invoice_id == invoice_id,
            CaseInvoiceAllocation.ledger_pair_id == ledger_pair_id),
        CaseInvoiceAllocation.amount_pence <= 0).limit(1))
    if invalid_previous is not None:
        raise HTTPException(409, "Existing allocations need review before allocating")
    invoice_total = int(db.scalar(select(func.coalesce(func.sum(CaseInvoiceAllocation.amount_pence), 0))
        .where(CaseInvoiceAllocation.invoice_id == invoice_id)))
    if invoice_total != int(inv.amount_allocated_pence or 0) or invoice_total < 0:
        raise HTTPException(409, "Invoice allocation totals are inconsistent; review them before allocating")
    source_total = int(db.scalar(select(func.coalesce(func.sum(CaseInvoiceAllocation.amount_pence), 0))
        .where(CaseInvoiceAllocation.ledger_pair_id == ledger_pair_id)))
    if source_total < 0:
        raise HTTPException(409, "Receipt allocation totals are inconsistent; review them before allocating")
    if amount_pence > int(inv.total_pence) - invoice_total:
        raise HTTPException(400, "Allocation exceeds the invoice's remaining balance")
    if amount_pence > credits[0].amount_pence - source_total:
        raise HTTPException(400, "Allocation exceeds the receipt's unallocated value")

    now = datetime.now(timezone.utc)
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
