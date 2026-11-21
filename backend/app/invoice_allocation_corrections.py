"""Audited whole-allocation reversals. Caller commits once, including the audit."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.audit import log_event
from app.deps import require_case_access
from app.invoice_allocation_integrity import invoice_consistency, require_consistent_totals, receipt_capacity, allocation_total, source_allocation_inconsistent
from app.ledger_integrity import lock_operation
from app.models import (CaseInvoice, CaseInvoiceAllocation, InvoiceAllocationReversal,
                        LedgerAccount, LedgerEntry, User)
from app.permission_checks import user_may_approve_ledger
from app.schemas.bank import InvoiceAllocationReversalIn
from app.timeutil import utcnow


def require_allocation_permission(db: Session, actor: User) -> None:
    if not actor.is_active or not user_may_approve_ledger(actor, db):
        raise HTTPException(403, 'Not permitted to correct invoice payments')


def authorise_source(db: Session, actor: User, pair_id: uuid.UUID) -> None:
    for case_id in db.scalars(select(LedgerAccount.case_id).join(LedgerEntry).where(
            LedgerEntry.pair_id == pair_id).distinct()):
        require_case_access(case_id, actor, db)


def locked_invoice(db: Session, invoice_id: uuid.UUID, actor: User) -> CaseInvoice:
    require_allocation_permission(db, actor)
    inv = db.get(CaseInvoice, invoice_id)
    if inv is None: raise HTTPException(404, 'Invoice not found')
    require_case_access(inv.case_id, actor, db)
    from app.invoice_service import _try_lock_invoice
    _try_lock_invoice(db, invoice_id)
    inv = db.scalar(select(CaseInvoice).where(CaseInvoice.id == invoice_id)
        .with_for_update().execution_options(populate_existing=True))
    if inv is None: raise HTTPException(404, 'Invoice not found')
    require_case_access(inv.case_id, actor, db)
    return inv


def reverse_allocation(db: Session, *, invoice_id: uuid.UUID, allocation_id: uuid.UUID,
                       payload: InvoiceAllocationReversalIn, actor: User) -> InvoiceAllocationReversal:
    require_allocation_permission(db, actor)
    if not payload.reason.strip(): raise HTTPException(400, 'A correction reason is required')
    # Request locks also prevent the same key being used concurrently on different invoices.
    lock_operation(db, 582013723, f'{actor.id}:{payload.idempotency_key}')
    inv = locked_invoice(db, invoice_id, actor)
    original = db.get(CaseInvoiceAllocation, allocation_id)
    if original is None or original.invoice_id != invoice_id:
        raise HTTPException(404, 'Allocation not found on this invoice')
    from app.ledger_service import _try_lock_ledger_pair
    _try_lock_ledger_pair(db, original.ledger_pair_id)
    authorise_source(db, actor, original.ledger_pair_id)
    previous = db.scalar(select(InvoiceAllocationReversal).where(
        InvoiceAllocationReversal.actor_user_id == actor.id,
        InvoiceAllocationReversal.idempotency_key == payload.idempotency_key))
    if previous:
        if previous.allocation_id != allocation_id or previous.reason != payload.reason.strip():
            raise HTTPException(409, 'This correction request ID was already used for different details')
        return previous
    if db.scalar(select(InvoiceAllocationReversal.id).where(InvoiceAllocationReversal.allocation_id == allocation_id)):
        raise HTTPException(409, 'This allocation has already been reversed')
    if inv.status != 'approved': raise HTTPException(409, 'Only allocations on approved invoices can be reversed')
    total = require_consistent_totals(db, inv)
    capacity, cases = receipt_capacity(db, original.ledger_pair_id)
    source_total = allocation_total(db, pair_id=original.ledger_pair_id)
    if (original.amount_pence <= 0 or cases != {inv.case_id} or source_total > capacity
            or source_total < original.amount_pence
            or source_allocation_inconsistent(db, original.ledger_pair_id, capacity, inv.case_id)):
        raise HTTPException(409, 'Receipt allocations are inconsistent; review before correcting')
    before = {'amount_allocated_pence': inv.amount_allocated_pence,
              'paid_at': inv.paid_at.isoformat() if inv.paid_at else None}
    row = InvoiceAllocationReversal(allocation_id=allocation_id, actor_user_id=actor.id,
        idempotency_key=payload.idempotency_key, reason=payload.reason.strip(), reversed_at=utcnow())
    db.add(row)
    inv.amount_allocated_pence = total - original.amount_pence
    # A positive whole-allocation reversal always makes a fully paid invoice unpaid.
    inv.paid_at = None
    db.flush()
    log_event(db, actor_user_id=actor.id, action='case.invoice.allocation.reverse', entity_type='invoice',
        entity_id=str(inv.id), meta={'case_id': str(inv.case_id), 'allocation_id': str(allocation_id),
        'reversal_id': str(row.id), 'ledger_pair_id': str(original.ledger_pair_id),
        'amount_pence': original.amount_pence, 'reason': row.reason, 'before': before,
        'after': {'amount_allocated_pence': inv.amount_allocated_pence, 'paid_at': None}})
    return row


def check_invoice_allocations(db: Session, *, invoice_id: uuid.UUID, actor: User) -> dict:
    inv = locked_invoice(db, invoice_id, actor)
    pairs = set(db.scalars(select(CaseInvoiceAllocation.ledger_pair_id).where(
        CaseInvoiceAllocation.invoice_id == invoice_id)))
    from app.ledger_service import _try_lock_ledger_pair
    for pair in sorted(pairs):
        _try_lock_ledger_pair(db, pair)
        authorise_source(db, actor, pair)
    return invoice_consistency(db, inv)
