"""Allocate client/office receipts against invoices for aged-debt accuracy."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CaseInvoice, CaseInvoiceAllocation, LedgerEntry, User
from app.permission_checks import user_may_approve_ledger
from app.timeutil import utcnow


def list_allocations(db: Session, invoice_id: uuid.UUID) -> list[CaseInvoiceAllocation]:
    return list(
        db.execute(
            select(CaseInvoiceAllocation)
            .where(CaseInvoiceAllocation.invoice_id == invoice_id)
            .order_by(CaseInvoiceAllocation.allocated_at)
        ).scalars().all()
    )


def allocate_to_invoice(
    db: Session,
    *,
    invoice_id: uuid.UUID,
    ledger_pair_id: uuid.UUID,
    amount_pence: int,
    actor: User,
    notes: str | None = None,
) -> CaseInvoiceAllocation:
    if not user_may_approve_ledger(actor, db):
        raise HTTPException(status_code=403, detail="Not permitted to allocate invoice payments")
    inv = db.get(CaseInvoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status != "approved":
        raise HTTPException(status_code=400, detail="Only approved invoices can receive allocations")
    leg = db.execute(
        select(LedgerEntry).where(LedgerEntry.pair_id == ledger_pair_id).limit(1)
    ).scalar_one_or_none()
    if leg is None or not leg.is_approved:
        raise HTTPException(status_code=400, detail="Ledger pair must be an approved posting")
    remaining = int(inv.total_pence) - int(inv.amount_allocated_pence or 0)
    if amount_pence > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Allocation exceeds remaining balance (£{remaining / 100:.2f})",
        )
    row = CaseInvoiceAllocation(
        id=uuid.uuid4(),
        invoice_id=invoice_id,
        ledger_pair_id=ledger_pair_id,
        amount_pence=amount_pence,
        allocated_by_user_id=actor.id,
        allocated_at=datetime.now(timezone.utc),
        notes=notes,
    )
    db.add(row)
    inv.amount_allocated_pence = int(inv.amount_allocated_pence or 0) + amount_pence
    if inv.amount_allocated_pence >= inv.total_pence:
        inv.paid_at = utcnow()
    db.add(inv)
    db.flush()
    return row
