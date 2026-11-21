"""Effective allocation values and read-only consistency diagnostics."""
import uuid
from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session
from app.models import (CaseInvoice, CaseInvoiceAllocation, InvoiceAllocationReversal,
                        LedgerAccount, LedgerAccountType, LedgerDirection, LedgerEntry)


def active_allocation():
    return ~exists(select(InvoiceAllocationReversal.id).where(
        InvoiceAllocationReversal.allocation_id == CaseInvoiceAllocation.id))


def allocation_total(db: Session, *, invoice_id=None, pair_id=None) -> int:
    query = select(func.coalesce(func.sum(CaseInvoiceAllocation.amount_pence), 0)).where(active_allocation())
    if invoice_id is not None: query = query.where(CaseInvoiceAllocation.invoice_id == invoice_id)
    if pair_id is not None: query = query.where(CaseInvoiceAllocation.ledger_pair_id == pair_id)
    return int(db.scalar(query))


def receipt_capacity(db: Session, pair_id: uuid.UUID) -> tuple[int, set[uuid.UUID]]:
    """Validate financial eligibility, leaving authorisation to the caller."""
    rows = list(db.execute(select(LedgerEntry, LedgerAccount).join(LedgerAccount).where(LedgerEntry.pair_id == pair_id)))
    cases = {account.case_id for _, account in rows}
    credits = [leg for leg, _ in rows if leg.direction == LedgerDirection.credit]
    kinds = [account.account_type for _, account in rows]
    valid = (len(rows) in (1, 2) and len(set(kinds)) == len(rows) and len(credits) == 1
             and len({leg.amount_pence for leg, _ in rows}) == 1
             and all(leg.is_approved and not leg.is_anticipated and leg.amount_pence > 0 for leg, _ in rows))
    if len(rows) == 2:
        valid = valid and all(leg.direction == (LedgerDirection.credit if account.account_type == LedgerAccountType.office
                                               else LedgerDirection.debit) for leg, account in rows)
    linked = db.scalar(select(CaseInvoice.id).where(or_(CaseInvoice.ledger_pair_id == pair_id,
                                                       CaseInvoice.reversal_pair_id == pair_id)).limit(1))
    if not valid or linked is not None:
        raise HTTPException(400, 'Allocation requires an approved, non-anticipated receipt or bill payment')
    from app.ledger_integrity import require_external_receipt
    require_external_receipt(db, pair_id)
    return credits[0].amount_pence, cases


def source_allocation_inconsistent(db: Session, pair_id: uuid.UUID, capacity: int, case_id: uuid.UUID) -> bool:
    total = allocation_total(db, pair_id=pair_id)
    invalid = db.scalar(select(CaseInvoiceAllocation.id).join(CaseInvoice).where(
        CaseInvoiceAllocation.ledger_pair_id == pair_id, active_allocation(),
        or_(CaseInvoiceAllocation.amount_pence <= 0, CaseInvoice.case_id != case_id,
            CaseInvoice.status != 'approved')).limit(1))
    return invalid is not None or total < 0 or total > capacity


def invoice_consistency(db: Session, invoice: CaseInvoice) -> dict:
    """No repairs or writes. Caller supplies a stable snapshot or relevant operation locks."""
    rows = list(db.scalars(select(CaseInvoiceAllocation).where(
        CaseInvoiceAllocation.invoice_id == invoice.id, active_allocation())))
    total = sum(row.amount_pence for row in rows)
    issues = []
    def issue(code, **details): issues.append({'code': code, **details})
    if total != invoice.amount_allocated_pence: issue('cached_total_mismatch')
    if any(row.amount_pence <= 0 for row in rows): issue('invalid_allocation_amount')
    if total < 0 or total > invoice.total_pence: issue('invoice_overallocated')
    if rows and invoice.status != 'approved': issue('allocated_invoice_not_approved')
    should_be_paid = invoice.status == 'approved' and invoice.total_pence > 0 and total == invoice.total_pence
    if bool(invoice.paid_at) != should_be_paid: issue('paid_status_mismatch')
    for pair in sorted({row.ledger_pair_id for row in rows}):
        try:
            capacity, cases = receipt_capacity(db, pair)
        except HTTPException:
            issue('invalid_receipt', ledger_pair_id=str(pair))
            continue
        if cases != {invoice.case_id}: issue('cross_matter_receipt', ledger_pair_id=str(pair))
        source_total = allocation_total(db, pair_id=pair)
        if source_total < 0 or source_total > capacity: issue('receipt_overallocated', ledger_pair_id=str(pair))
        elif source_allocation_inconsistent(db, pair, capacity, invoice.case_id):
            issue('receipt_allocations_inconsistent', ledger_pair_id=str(pair))
    return {'invoice_id': str(invoice.id), 'consistent': not issues, 'active_allocated_pence': total,
            'cached_allocated_pence': invoice.amount_allocated_pence, 'issues': issues}


def require_consistent_totals(db: Session, invoice: CaseInvoice) -> int:
    total = allocation_total(db, invoice_id=invoice.id)
    should_be_paid = invoice.status == 'approved' and invoice.total_pence > 0 and total == invoice.total_pence
    invalid = db.scalar(select(CaseInvoiceAllocation.id).where(CaseInvoiceAllocation.invoice_id == invoice.id,
        active_allocation(), CaseInvoiceAllocation.amount_pence <= 0).limit(1))
    if (invalid or total != invoice.amount_allocated_pence or total < 0 or total > invoice.total_pence
            or bool(invoice.paid_at) != should_be_paid or (total and invoice.status != 'approved')):
        raise HTTPException(409, 'Invoice allocations or paid status are inconsistent; run the consistency check before correcting')
    return total
