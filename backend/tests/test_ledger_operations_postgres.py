"""Real transaction races on disposable PostgreSQL only."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Case, User, LedgerEntry, LedgerOperation
from app.schemas import LedgerPostCreate
from app import ledger_operations as operations
from app import inter_matter_journal_service as transfers
from tests.test_ledger_operations import fixture, post, transfer_payload, reversal, balance


@pytest.mark.parametrize('race', ['duplicate_post', 'duplicate_transfer', 'shared_funds',
    'opposite_transfer', 'reverse_post', 'reverse_transfer', 'rollback', 'first_accounts'])
def test_concurrent_movements(db, race):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires isolated PostgreSQL')
    _, user, first, second = fixture(db)
    original = None
    if race != 'first_accounts': original = post(db, user, first)
    if race == 'opposite_transfer': post(db, user, second)
    journal = None
    if race == 'reverse_transfer': journal = transfers.create_inter_matter_journal(db,
        payload=transfer_payload(first, second), user=user)
    db.commit()
    uid, first_id, second_id = user.id, first.id, second.id
    original_id = original.pair_id if original else None
    journal_id = journal.id if journal else None
    receipt = LedgerPostCreate(description='Concurrent posting', amount_pence=8000,
        client_direction='debit' if race == 'shared_funds' else 'credit', idempotency_key=uuid.uuid4())
    journal_payload = transfer_payload(first, second)
    reverse_payload = reversal()
    locked, attempted = Event(), Event()

    def perform(session, contender=False):
        actor = session.get(User, uid)
        if race in ('duplicate_transfer', 'opposite_transfer', 'rollback'):
            payload = journal_payload
            if contender and race == 'opposite_transfer':
                payload = payload.model_copy(update={'from_case_id': second_id, 'to_case_id': first_id,
                                                     'idempotency_key': uuid.uuid4()})
            return transfers.create_inter_matter_journal(session, payload=payload, user=actor).id
        if race == 'reverse_post':
            return operations.reverse_posting(session, case_id=first_id, pair_id=original_id,
                payload=reverse_payload if not contender else reversal(), user=actor)['pair_id']
        if race == 'reverse_transfer':
            return transfers.reverse_inter_matter_journal(session, journal_id=journal_id,
                payload=reverse_payload if not contender else reversal(), user=actor).id
        payload = receipt
        if contender and race in ('shared_funds', 'first_accounts'): payload = receipt.model_copy(update={'idempotency_key': uuid.uuid4()})
        return operations.post_ledger_operation(first_id, payload, actor, session).pair_id

    def winner():
        with SessionLocal() as session:
            result = perform(session)
            locked.set()
            assert attempted.wait(15)
            if race == 'rollback': session.rollback()
            else: session.commit()
            return result

    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error: perform(session, True)
                assert error.value.status_code == 409
        finally: attempted.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(winner), pool.submit(contender)
        won = a.result(20); b.result(20)
    with SessionLocal() as session:
        if race in ('shared_funds', 'reverse_post', 'reverse_transfer'):
            with pytest.raises(HTTPException) as error: perform(session, True)
            assert error.value.status_code == (422 if race == 'shared_funds' else 409)
            session.rollback()
        else:
            retried = perform(session, True)
            if race in ('duplicate_post', 'duplicate_transfer'): assert retried == won
            session.commit()
        a, b = session.get(Case, first_id), session.get(Case, second_id)
        expected = {'duplicate_post': (18000, 0), 'duplicate_transfer': (6000, 4000),
            'shared_funds': (2000, 0), 'opposite_transfer': (10000, 10000), 'reverse_post': (0, 0),
            'reverse_transfer': (10000, 0), 'rollback': (6000, 4000), 'first_accounts': (16000, 0)}
        assert (balance(session, a), balance(session, b)) == expected[race]
        assert session.scalar(select(func.count()).select_from(LedgerOperation).where(
            LedgerOperation.actor_user_id == uid, LedgerOperation.request_key == receipt.idempotency_key)) <= 1


def test_durable_request_uniqueness(db):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires isolated PostgreSQL')
    _, user, first, _ = fixture(db)
    result = post(db, user, first); db.commit()
    row = db.scalar(select(LedgerOperation).where(LedgerOperation.result_id == result.pair_id))
    db.add(LedgerOperation(actor_user_id=user.id, request_key=row.request_key, kind=row.kind,
        fingerprint=row.fingerprint, result_id=uuid.uuid4(), result_json=row.result_json))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()


@pytest.mark.parametrize('dependency', ['allocation', 'bank_match'])
@pytest.mark.parametrize('reverse_wins', [True, False])
def test_reversal_serializes_with_financial_dependencies(db, dependency, reverse_wins):
    if db.bind.dialect.name != 'postgresql': pytest.skip('requires isolated PostgreSQL')
    from tests.test_invoice_allocation import allocation_fixture, allocate
    from tests.test_bank_integrity import fixture as bank_fixture, match
    from app.models import CaseInvoice, BankStatementLine
    if dependency == 'allocation':
        _, user, matter, invoice, pair = allocation_fixture(db)
        dependent_id = invoice.id
    else:
        _, user, matter, _, _, _, line, leg = bank_fixture(db)
        pair, dependent_id = leg.pair_id, line.id
    db.commit()
    uid, cid = user.id, matter.id
    locked, attempted = Event(), Event()
    def perform(session, reverse):
        actor = session.get(User, uid)
        if reverse: operations.reverse_posting(session, case_id=cid, pair_id=pair, payload=reversal(), user=actor)
        elif dependency == 'allocation': allocate(session, actor, session.get(CaseInvoice, dependent_id), pair)
        else:
            from app.bank_matching_service import match_line
            match_line(session, line_id=dependent_id, ledger_pair_id=pair, actor=actor, expected_version=0)
    def winner():
        with SessionLocal() as session:
            perform(session, reverse_wins)
            locked.set()
            assert attempted.wait(15)
            session.commit()
    def contender():
        assert locked.wait(15)
        try:
            with SessionLocal() as session:
                with pytest.raises(HTTPException) as error: perform(session, not reverse_wins)
                assert error.value.status_code == 409
        finally: attempted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(winner), pool.submit(contender)
        a.result(20); b.result(20)
    with SessionLocal() as session:
        with pytest.raises(HTTPException) as error: perform(session, not reverse_wins)
        assert error.value.status_code == 409
