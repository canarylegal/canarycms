"""Actual PostgreSQL period transitions must serialize with financial writes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import date
import pytest
from fastapi import HTTPException
from app.db import SessionLocal
from app.models import ClientAccountReconciliation,User
from app.reconciliation_service import approve_reconciliation,firm_wide_ledger_totals
from app.period_reopening import preview_reopening,reopen_period
from app.ledger_service import post_transaction
from app.schemas import LedgerPostCreate
from tests.test_ledger_operations import fixture
from tests.test_accounting_periods import close_period


@pytest.mark.parametrize('write_kind',['office','allocation','allocation_reversal','transfer'])
@pytest.mark.parametrize('winner_kind',['approval','posting','posting_rollback','reopen'])
def test_period_transition_and_posting_cannot_cross(db,winner_kind,write_kind):
    if db.bind.dialect.name!='postgresql':pytest.skip('isolated PostgreSQL required')
    _,user,matter,other=fixture(db);db.commit()
    from tests.test_invoice_allocation import new_invoice,allocate
    from tests.test_invoice_corrections import reverse
    from tests.test_ledger_operations import post,transfer_payload
    from app.inter_matter_journal_service import create_inter_matter_journal
    from app.models import CaseInvoice,CaseInvoiceAllocation
    iid=pair=aid=None
    if write_kind in ('allocation','allocation_reversal'):
        invoice=new_invoice(db,matter.id,user.id)
        payment=post_transaction(matter.id,LedgerPostCreate(description='Synthetic receipt',amount_pence=10000,office_direction='credit'),user,db)
        iid,pair=invoice.id,payment.pair_id
        if write_kind=='allocation_reversal':aid=allocate(db,user,invoice,pair,1000).id
    if write_kind=='transfer':post(db,user,matter)
    transfer=transfer_payload(matter,other)
    db.commit()
    row=close_period(db,user,approved=winner_kind=='reopen')
    row.notes='Synthetic difference reviewed';db.commit()
    uid,cid,rid=user.id,matter.id,row.id
    baseline=firm_wide_ledger_totals(db,date(2099,1,31))[1]
    preview=preview_reopening(db,rid);db.rollback()
    locked,attempted=Event(),Event()
    def write(session):
        actor=session.get(User,uid)
        if write_kind=='allocation':allocate(session,actor,session.get(CaseInvoice,iid),pair,1000)
        elif write_kind=='allocation_reversal':reverse(session,actor,session.get(CaseInvoice,iid),session.get(CaseInvoiceAllocation,aid))
        elif write_kind=='transfer':create_inter_matter_journal(session,payload=transfer,user=actor)
        else:post_transaction(cid,LedgerPostCreate(description='Synthetic period race',amount_pence=100,
            office_direction='credit'),actor,session)
    def approve(session):
        target=session.get(ClientAccountReconciliation,rid)
        approve_reconciliation(session,actor=session.get(User,uid),row=target)
    def winner():
        with SessionLocal() as session:
            if winner_kind=='approval':approve(session)
            elif winner_kind=='reopen':reopen_period(session,reconciliation_id=rid,actor_id=uid,
                expected_hash=preview['preview_hash'],reason='Synthetic concurrent review')
            else:write(session)
            locked.set()
            assert attempted.wait(15)
            if winner_kind=='posting_rollback':session.rollback()
            else:session.commit()
    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error:
                    if winner_kind in ('approval','reopen'):write(session)
                    else:approve(session)
                assert error.value.status_code==409
        finally:attempted.set()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a,b=pool.submit(winner),pool.submit(contender)
            a.result(20);b.result(20)
        with SessionLocal() as session:
            if winner_kind=='approval':
                with pytest.raises(HTTPException):write(session)
                session.rollback()
            elif winner_kind=='reopen':
                write(session);session.commit()
            else:
                approve(session);session.commit()
                assert session.get(ClientAccountReconciliation,rid).ledger_office_total_pence==baseline+(100 if winner_kind=='posting' and write_kind=='office' else 0)
    finally:
        # Remove only this synthetic future cutoff, never deployment data.
        with SessionLocal() as session:
            target=session.get(ClientAccountReconciliation,rid)
            assert target.prepared_by_user_id==uid and target.period_end_date==date(2099,1,31)
            session.delete(target);session.commit()
