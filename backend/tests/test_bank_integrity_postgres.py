"""Run against the disposable migrated PostgreSQL stack, never deployment data."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app import bank_recon_service as service
from app.db import SessionLocal
from app.models import BankStatementLine, BankReconciliation, User, AuditEvent
from tests.test_bank_integrity import fixture, new_line, new_leg, PERIOD


@pytest.mark.parametrize('race', ['same_payment', 'same_line', 'rollback', 'approve', 'closed_period', 'create'])
def test_bank_transactions_serialize(db, race):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires disposable PostgreSQL')
    _, user, _, bank, account, imp, line, leg = fixture(db)
    other = new_line(db, imp)
    other_leg = new_leg(db, account, bank, user)
    if race == 'closed_period':
        service.match_line(db, line_id=line.id, ledger_pair_id=leg.pair_id, actor=user, expected_version=0)
    row = None
    if race in ('approve', 'closed_period'):
        row = service.create_bank_reconciliation(db, actor=user, firm_bank_account_id=bank.id,
            period_end_date=PERIOD, statement_balance_pence=20000, notes='Synthetic concurrency fixture')
    db.commit()
    uid, bid, lid, oid, pair, other_pair = user.id, bank.id, line.id, other.id, leg.pair_id, other_leg.pair_id
    rid = row.id if row else None
    locked, attempted = Event(), Event()

    def create(session, actor):
        return service.create_bank_reconciliation(session, actor=actor, firm_bank_account_id=bid,
            period_end_date=PERIOD, statement_balance_pence=20000, notes=None)

    def winner():
        with SessionLocal() as session:
            actor = session.get(User, uid)
            if race == 'closed_period':
                service.approve_bank_reconciliation(session, row=session.get(BankReconciliation, rid), actor=actor, expected_version=0)
            elif race == 'create': create(session, actor)
            else: service.match_line(session, line_id=lid, ledger_pair_id=pair, actor=actor, expected_version=0)
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
                    if race == 'approve':
                        service.approve_bank_reconciliation(session, row=session.get(BankReconciliation, rid), actor=actor, expected_version=0)
                    elif race == 'closed_period':
                        service.unmatch_line(session, line_id=lid, actor=actor, expected_version=1)
                    elif race == 'create': create(session, actor)
                    else:
                        service.match_line(session, line_id=lid if race == 'same_line' else oid,
                            ledger_pair_id=other_pair if race == 'same_line' else pair, actor=actor, expected_version=0)
                assert error.value.status_code == 409
        finally: attempted.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(winner), pool.submit(contender)
        first.result(20); second.result(20)
    with SessionLocal() as session:
        actor = session.get(User, uid)
        if race == 'rollback':
            service.match_line(session, line_id=lid, ledger_pair_id=pair, actor=actor, expected_version=0)
            session.commit()
        elif race == 'approve':
            service.approve_bank_reconciliation(session, row=session.get(BankReconciliation, rid), actor=actor, expected_version=0)
            session.commit()
        else:
            with pytest.raises(HTTPException) as error:
                if race == 'closed_period': service.unmatch_line(session, line_id=lid, actor=actor, expected_version=1)
                elif race == 'create': create(session, actor)
                else: service.match_line(session, line_id=oid if race == 'same_payment' else lid,
                    ledger_pair_id=pair if race == 'same_payment' else other_pair, actor=actor, expected_version=0)
            assert error.value.status_code == 409
            session.rollback()
        if race != 'create':
            assert session.get(BankStatementLine, lid).matched_pair_id == pair
            assert session.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.entity_id == str(lid), AuditEvent.action == 'bank.statement.match')) == 1


def test_database_constraint_rejects_duplicate_matches(db):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires disposable PostgreSQL')
    _, user, _, _, _, imp, line, leg = fixture(db)
    other = new_line(db, imp)
    service.match_line(db, line_id=line.id, ledger_pair_id=leg.pair_id, actor=user, expected_version=0)
    db.commit()
    other.matched_pair_id = leg.pair_id
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.refresh(other)
    assert other.matched_pair_id is None


def test_large_complete_balances_fit_migrated_reconciliation_columns(db):
    from app.reconciliation_service import create_reconciliation
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires disposable PostgreSQL')
    _, user, _, bank, account, _, _, leg = fixture(db)
    leg.amount_pence = 1500000000
    new_leg(db, account, bank, user, 1500000000)
    row = service.create_bank_reconciliation(db, actor=user, firm_bank_account_id=bank.id,
        period_end_date=PERIOD, statement_balance_pence=10000, notes=None)
    db.commit()
    db.refresh(row)
    assert row.ledger_total_pence == 3000000000 and row.unpresented_total_pence == 3000000000
    assert row.difference_pence == 0
    report = create_reconciliation(db, actor=user, period_end_date=PERIOD,
        bank_statement_balance_pence=3000000000, notes='Synthetic aggregate range test')
    db.commit()
    db.refresh(report)
    assert report.ledger_client_total_pence >= 3000000000
