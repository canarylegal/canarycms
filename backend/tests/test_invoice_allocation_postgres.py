"""Concurrency checks on the disposable migrated PostgreSQL stack only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.db import SessionLocal
from app.models import CaseInvoice, CaseInvoiceAllocation, User
from app.invoice_allocation_service import allocate_to_invoice
from app.invoice_service import void_case_invoice
from tests.test_invoice_allocation import allocation_fixture, new_invoice


@pytest.mark.parametrize('race', ['same_receipt', 'same_invoice', 'retry', 'void', 'rollback'])
def test_allocation_transactions_serialize(db, race):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('requires disposable PostgreSQL')
    _, user, case, invoice, pair = allocation_fixture(db)
    second = new_invoice(db, case.id, user.id) if race == 'same_receipt' else invoice
    contender_pair = pair
    if race == 'same_invoice':
        from app.ledger_service import post_transaction
        from app.schemas import LedgerPostCreate
        contender_pair = post_transaction(case.id, LedgerPostCreate(description='Second receipt',
            amount_pence=10000, office_direction='credit', contact_label='N/A'), user, db).pair_id
    db.commit()
    uid, iid, second_id, cid = user.id, invoice.id, second.id, case.id
    key = uuid.uuid4()
    locked, attempted = Event(), Event()

    def winner():
        with SessionLocal() as session:
            allocate_to_invoice(session, invoice_id=iid, ledger_pair_id=pair, amount_pence=10000,
                actor=session.get(User, uid), idempotency_key=key)
            locked.set()
            assert attempted.wait(15)
            if race == 'rollback': session.rollback()
            else: session.commit()

    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                actor = session.get(User, uid)
                with pytest.raises(HTTPException) as error:
                    if race == 'void':
                        void_case_invoice(cid, iid, actor, session)
                    else:
                        allocate_to_invoice(session, invoice_id=second_id, ledger_pair_id=contender_pair,
                            amount_pence=10000, actor=actor, idempotency_key=key if race == 'retry' else uuid.uuid4())
                assert error.value.status_code == 409
        finally:
            attempted.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second_job = pool.submit(winner), pool.submit(contender)
        first.result(20)
        second_job.result(20)
    with SessionLocal() as session:
        actor = session.get(User, uid)
        if race in ('retry', 'rollback'):
            allocate_to_invoice(session, invoice_id=iid, ledger_pair_id=pair, amount_pence=10000,
                actor=actor, idempotency_key=key)
            session.commit()
        else:
            with pytest.raises(HTTPException):
                if race == 'void': void_case_invoice(cid, iid, actor, session)
                else: allocate_to_invoice(session, invoice_id=second_id, ledger_pair_id=contender_pair,
                    amount_pence=1, actor=actor)
            session.rollback()
        assert session.scalar(select(func.count()).select_from(CaseInvoiceAllocation).where(
            CaseInvoiceAllocation.ledger_pair_id == pair)) == 1
        assert session.get(CaseInvoice, iid).amount_allocated_pence == 10000


def test_migrated_database_rejects_invalid_values_and_duplicate_requests(db):
    from sqlalchemy.exc import IntegrityError
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('requires disposable PostgreSQL')
    _, user, _, inv, pair = allocation_fixture(db)
    uid, iid = user.id, inv.id
    key = uuid.uuid4()
    for amount in (0, -1):
        db.add(CaseInvoiceAllocation(invoice_id=iid, ledger_pair_id=pair,
            amount_pence=amount, allocated_by_user_id=uid))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
    allocate_to_invoice(db, invoice_id=iid, ledger_pair_id=pair, amount_pence=100,
        actor=db.get(User, uid), idempotency_key=key)
    db.commit()
    db.add(CaseInvoiceAllocation(invoice_id=iid, ledger_pair_id=pair,
        amount_pence=100, allocated_by_user_id=uid, idempotency_key=key))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    assert db.get(CaseInvoice, iid).amount_allocated_pence == 100
