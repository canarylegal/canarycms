"""Real transaction races on synthetic data in the isolated workflow database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import User, BankStatementLine, AuditEvent, BankReconciliation
from app import bank_recon_service as banking
from app.historical_corrections import preview_unmatch, apply_unmatch, ACTION
from tests.test_historical_corrections import fixture
from tests.test_bank_integrity import PERIOD


@pytest.mark.parametrize('winner_kind',['correction','rollback','ordinary_unmatch','period_approval'])
def test_correction_serializes_with_bank_operations(db,winner_kind):
    if db.bind.dialect.name!='postgresql':pytest.skip('isolated PostgreSQL required')
    _,user,bank,line,_=fixture(db)
    reconciliation=banking.create_bank_reconciliation(db,actor=user,firm_bank_account_id=bank.id,
        period_end_date=PERIOD,statement_balance_pence=0,notes='Synthetic reconciliation test')
    db.commit()
    uid,lid,rid=user.id,line.id,reconciliation.id
    plan=preview_unmatch(db,lid);db.rollback()
    locked,attempted=Event(),Event()
    def correct(session):
        return apply_unmatch(session,plan=plan,actor_id=uid,reason='Reviewed synthetic missing posting',approved_hash=plan['plan_hash'])
    def winner():
        with SessionLocal() as session:
            actor=session.get(User,uid)
            if winner_kind=='ordinary_unmatch':banking.unmatch_line(session,line_id=lid,actor=actor,expected_version=0)
            elif winner_kind=='period_approval':banking.approve_bank_reconciliation(session,actor=actor,row=session.get(BankReconciliation,rid),expected_version=0)
            else:correct(session)
            locked.set()
            assert attempted.wait(15)
            if winner_kind=='rollback':session.rollback()
            else:session.commit()
    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error:correct(session)
                assert error.value.status_code==409
        finally:attempted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=pool.submit(winner),pool.submit(contender)
        a.result(20);b.result(20)
    with SessionLocal() as session:
        if winner_kind in ('ordinary_unmatch','period_approval'):
            with pytest.raises(HTTPException):correct(session)
            session.rollback()
        else:
            result=correct(session)
            assert result['status']==('applied' if winner_kind=='rollback' else 'already_applied')
            session.commit()
            assert session.get(BankStatementLine,lid).version==1
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action==ACTION,AuditEvent.entity_id==plan['plan_hash']))==1
        # Clear only the synthetic dangling match after proving the closed-period guard.
        if winner_kind=='period_approval':
            row=session.get(BankReconciliation,rid)
            banking.reopen_bank_reconciliation(session,actor=session.get(User,uid),row=row,expected_version=row.version,reason='Synthetic test cleanup')
            session.commit()
            refreshed=preview_unmatch(session,lid)
            apply_unmatch(session,plan=refreshed,actor_id=uid,reason='Synthetic test cleanup after reopened period',approved_hash=refreshed['plan_hash'])
            session.commit()
