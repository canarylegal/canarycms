"""Replay a correction from separate processes across an isolated backend restart."""
import json
import os
import uuid
from sqlalchemy import func, select
from app.db import SessionLocal
from app.models import User, Case, CaseInvoice, AuditEvent
from app.schemas import LedgerPostCreate
from app.schemas.bank import InvoiceAllocationReversalIn
from app.ledger_operations import post_ledger_operation
from app.invoice_allocation_service import allocate_to_invoice
from app.invoice_allocation_corrections import reverse_allocation

if os.getenv('CANARY_TEST_FIXTURE') != '1' or os.getenv('POSTGRES_DB') != 'canary_core_test':
    raise SystemExit('Requires the disposable core fixture')
with SessionLocal() as db:
    actor = db.scalar(select(User).where(User.email == 'core.approver@example.com'))
    matter = db.scalar(select(Case).where(Case.case_number == '900001'))
    assert actor is not None and matter is not None
    iid = uuid.UUID('673cbb3c-b828-4b8d-99ab-0071c1596101')
    inv = db.get(CaseInvoice, iid)
    if inv is None:
        inv = CaseInvoice(id=iid, case_id=matter.id, invoice_number='CI-ALLOCATION-RESTART', status='approved',
                          total_pence=100, amount_allocated_pence=0, created_by_user_id=actor.id)
        db.add(inv); db.flush()
    result = post_ledger_operation(matter.id, LedgerPostCreate(description='Correction restart receipt',
        amount_pence=100, office_direction='credit', idempotency_key=uuid.UUID('673cbb3c-b828-4b8d-99ab-0071c1596102')), actor, db)
    allocation = allocate_to_invoice(db, invoice_id=iid, ledger_pair_id=result.pair_id, amount_pence=100,
        actor=actor, idempotency_key=uuid.UUID('673cbb3c-b828-4b8d-99ab-0071c1596103'))
    correction = reverse_allocation(db, invoice_id=iid, allocation_id=allocation.id, actor=actor,
        payload=InvoiceAllocationReversalIn(idempotency_key=uuid.UUID('673cbb3c-b828-4b8d-99ab-0071c1596104'), reason='Restart drill'))
    db.commit()
    assert inv.amount_allocated_pence == 0 and inv.paid_at is None
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == str(iid),
        AuditEvent.action == 'case.invoice.allocation.reverse')) == 1
    print(json.dumps({'allocation_id': str(allocation.id), 'reversal_id': str(correction.id), 'active_allocated_pence': 0}))
