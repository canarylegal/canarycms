"""Correction races on an isolated migrated PostgreSQL database."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from app.db import SessionLocal
from app.models import User, CaseInvoice, CaseInvoiceAllocation, InvoiceAllocationReversal, AuditEvent
from app.invoice_allocation_corrections import reverse_allocation, check_invoice_allocations
from app.invoice_allocation_service import allocate_to_invoice
from app.invoice_allocation_integrity import allocation_total
from app.invoice_service import void_case_invoice
from app.ledger_operations import reverse_posting
from app.schemas.ledger import LedgerReversalCreate
from tests.test_invoice_corrections import fixture, payload
from tests.test_invoice_allocation import new_invoice


@pytest.mark.parametrize('race', ['same_request', 'new_request', 'reallocate', 'void', 'ledger_reverse', 'rollback', 'consistency'])
def test_correction_transactions_serialize(db, race):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires disposable PostgreSQL')
    _, user, matter, invoice, pair, original = fixture(db)
    target = new_invoice(db, matter.id, user.id)
    db.commit()
    uid, iid, aid, cid, target_id = user.id, invoice.id, original.id, matter.id, target.id
    request = payload()
    locked, attempted = Event(), Event()
    def correct(session, data=request):
        return reverse_allocation(session, invoice_id=iid, allocation_id=aid, payload=data, actor=session.get(User, uid))
    def competing(session):
        actor = session.get(User, uid)
        if race == 'void': void_case_invoice(cid, iid, actor, session)
        elif race == 'ledger_reverse': reverse_posting(session, case_id=cid, pair_id=pair,
            payload=LedgerReversalCreate(idempotency_key=uuid.uuid4(), reason='Correct receipt'), user=actor)
        elif race == 'reallocate': allocate_to_invoice(session, invoice_id=target_id, ledger_pair_id=pair,
            amount_pence=10000, actor=actor, idempotency_key=uuid.uuid4())
        elif race == 'consistency': check_invoice_allocations(session, invoice_id=iid, actor=actor)
        else: correct(session, payload() if race == 'new_request' else request)
    def winner():
        with SessionLocal() as session:
            correct(session)
            locked.set()
            assert attempted.wait(15)
            if race == 'rollback': session.rollback()
            else: session.commit()
    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error: competing(session)
                assert error.value.status_code == 409
        finally: attempted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(winner), pool.submit(contender)
        a.result(20); b.result(20)
    with SessionLocal() as session:
        if race == 'new_request':
            with pytest.raises(HTTPException) as error: competing(session)
            assert error.value.status_code == 409
            session.rollback()
        elif race == 'void':
            # Void is permitted only after also correcting the actual receipt and retaining the charge.
            from app.ledger_service import post_transaction
            from app.schemas import LedgerPostCreate
            actor = session.get(User, uid)
            inv = session.get(CaseInvoice, iid)
            inv.ledger_pair_id = post_transaction(cid, LedgerPostCreate(description='Invoice charge',
                amount_pence=10000, office_direction='debit'), actor, session).pair_id
            reverse_posting(session, case_id=cid, pair_id=pair,
                payload=LedgerReversalCreate(idempotency_key=uuid.uuid4(), reason='Correct receipt'), user=actor)
            session.commit()
            competing(session); session.commit()
            assert session.get(CaseInvoice, iid).status == 'voided'
        else:
            competing(session); session.commit()
        assert session.get(CaseInvoice, iid).amount_allocated_pence == 0
        assert session.get(CaseInvoice, iid).paid_at is None
        assert allocation_total(session, pair_id=pair) == (10000 if race == 'reallocate' else 0)
        assert session.scalar(select(func.count()).select_from(InvoiceAllocationReversal).where(
            InvoiceAllocationReversal.allocation_id == aid)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.entity_id == str(iid), AuditEvent.action == 'case.invoice.allocation.reverse')) == 1
        assert session.get(CaseInvoiceAllocation, aid).amount_pence == 10000


def test_database_constraints_preserve_one_correction_and_request(db):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires disposable PostgreSQL')
    _, user, matter, inv, pair, original = fixture(db)
    request = payload()
    row = reverse_allocation(db, invoice_id=inv.id, allocation_id=original.id, payload=request, actor=user)
    db.commit()
    other = allocate_to_invoice(db, invoice_id=inv.id, ledger_pair_id=pair, amount_pence=1000, actor=user)
    db.commit()
    uid, aid, other_id, key = user.id, original.id, other.id, request.idempotency_key
    for allocation, request_key, reason in [(aid, uuid.uuid4(), 'Duplicate original'),
                                           (other_id, key, 'Duplicate request'), (other_id, uuid.uuid4(), '   ')]:
        db.add(InvoiceAllocationReversal(allocation_id=allocation, actor_user_id=uid,
            idempotency_key=request_key, reason=reason))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
    assert db.scalar(select(func.count()).select_from(InvoiceAllocationReversal).where(
        InvoiceAllocationReversal.allocation_id.in_([aid, other_id]))) == 1
    assert db.get(CaseInvoice, inv.id).amount_allocated_pence == 1000


def test_request_key_serializes_corrections_on_different_invoices(db):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires disposable PostgreSQL')
    from app.ledger_service import post_transaction
    from app.schemas import LedgerPostCreate
    _, user, matter, invoice, _, original = fixture(db)
    other = new_invoice(db, matter.id, user.id)
    pair = post_transaction(matter.id, LedgerPostCreate(description='Second receipt',
        amount_pence=10000, office_direction='credit'), user, db).pair_id
    other_allocation = allocate_to_invoice(db, invoice_id=other.id, ledger_pair_id=pair, amount_pence=10000, actor=user)
    db.commit()
    uid, iid, aid, other_iid, other_aid = user.id, invoice.id, original.id, other.id, other_allocation.id
    request = payload()
    locked, attempted = Event(), Event()
    def run(session, inv, allocation):
        return reverse_allocation(session, invoice_id=inv, allocation_id=allocation,
            payload=request, actor=session.get(User, uid))
    def winner():
        with SessionLocal() as session:
            run(session, iid, aid)
            locked.set()
            assert attempted.wait(15)
            session.commit()
    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error: run(session, other_iid, other_aid)
                assert error.value.status_code == 409
        finally: attempted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(winner), pool.submit(contender)
        a.result(20); b.result(20)
    with SessionLocal() as session:
        with pytest.raises(HTTPException) as error: run(session, other_iid, other_aid)
        assert error.value.status_code == 409
        assert session.get(CaseInvoice, other_iid).amount_allocated_pence == 10000
