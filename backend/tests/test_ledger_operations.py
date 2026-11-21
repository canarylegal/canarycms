"""Financial outcomes: access, retry, failure rollback and linked compensation."""
import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app import inter_matter_journal_service as transfers
from app import ledger_operations as operations
from app.bank_accounts_service import create_bank_account
from app.ledger_integrity import require_external_receipt
from app.ledger_service import _balance, _get_or_create_accounts, approve_ledger_pair
from app.models import (AuditEvent, CaseLockMode, InterMatterJournal, LedgerEntry, LedgerOperation, UserRole)
from app.schemas import LedgerPostCreate
from app.schemas.bank import InterMatterJournalCreate
from app.schemas.ledger import LedgerReversalCreate
from tests.ledger_test_helpers import add_case, add_cashier_category, add_user, ledger_test_session


def fixture(db=None):
    db = db if db is not None else ledger_test_session()
    actor = add_user(db)
    first = add_case(db, fee_earner_user_id=actor.id)
    second = add_case(db, fee_earner_user_id=actor.id)
    return db, actor, first, second


def post(db, actor, matter, amount=10000, direction='credit', **kw):
    payload = LedgerPostCreate(description='Synthetic integrity test', amount_pence=amount,
        client_direction=direction, idempotency_key=uuid.uuid4(), **kw)
    return operations.post_ledger_operation(matter.id, payload, actor, db)


def transfer_payload(first, second, **kw):
    return InterMatterJournalCreate(from_case_id=first.id, to_case_id=second.id, amount_pence=4000,
        description='Synthetic transfer', idempotency_key=uuid.uuid4(), **kw)


def reversal():
    return LedgerReversalCreate(idempotency_key=uuid.uuid4(), reason='Correct synthetic posting')


def balance(db, matter):
    return _balance(_get_or_create_accounts(matter.id, db)['client'].id, db)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize('amount', [True, 1.5, '100', 0, -1, 2147483648])
def test_money_is_bounded_integer(amount):
    with pytest.raises(ValidationError): LedgerPostCreate(description='x', amount_pence=amount)
    with pytest.raises(ValidationError): InterMatterJournalCreate(from_case_id=uuid.uuid4(),
        to_case_id=uuid.uuid4(), description='x', amount_pence=amount)


def test_post_lost_response_retry_and_changed_request():
    db, user, first, _ = fixture()
    payload = LedgerPostCreate(description='Receipt', amount_pence=10000, client_direction='credit', idempotency_key=uuid.uuid4())
    result = operations.post_ledger_operation(first.id, payload, user, db)
    db.commit()
    assert operations.post_ledger_operation(first.id, payload, user, db) == result
    assert count(db, LedgerEntry) == count(db, LedgerOperation) == count(db, AuditEvent) == 1
    with pytest.raises(HTTPException) as error:
        operations.post_ledger_operation(first.id, payload.model_copy(update={'amount_pence': 20000}), user, db)
    assert error.value.status_code == 409


@pytest.mark.parametrize('endpoint', ['source', 'destination'])
def test_transfer_rechecks_both_matters_before_retry(endpoint):
    db, _, first, second = fixture()
    category = add_cashier_category(db)
    user = add_user(db, role=UserRole.user, permission_category_id=category.id)
    post(db, user, first)
    payload = transfer_payload(first, second)
    result = transfers.create_inter_matter_journal(db, payload=payload, user=user)
    db.commit()
    assert transfers.create_inter_matter_journal(db, payload=payload, user=user).id == result.id
    (first if endpoint == 'source' else second).lock_mode = CaseLockMode.allow_list
    db.commit()
    with pytest.raises(HTTPException) as error:
        transfers.create_inter_matter_journal(db, payload=payload, user=user)
    assert error.value.status_code == 403
    assert balance(db, first) == 6000 and balance(db, second) == 4000


@pytest.mark.parametrize('failure', ['second_leg', 'audit', 'receipt'])
def test_transfer_failure_rolls_back_both_legs_and_retry(failure, monkeypatch):
    db, user, first, second = fixture()
    post(db, user, first); db.commit()
    payload = transfer_payload(first, second)
    before = (count(db, LedgerEntry), count(db, AuditEvent), count(db, LedgerOperation))
    def fail(*args, **kw): raise RuntimeError('injected failure')
    with monkeypatch.context() as patch:
        if failure == 'second_leg':
            original = transfers.post_transaction
            def second_leg(case_id, *args, **kw):
                if case_id == second.id: fail()
                return original(case_id, *args, **kw)
            patch.setattr(transfers, 'post_transaction', second_leg)
        else: patch.setattr(transfers, 'log_event' if failure == 'audit' else 'record_receipt', fail)
        with pytest.raises(RuntimeError): transfers.create_inter_matter_journal(db, payload=payload, user=user)
        db.rollback()
    assert (count(db, LedgerEntry), count(db, AuditEvent), count(db, LedgerOperation)) == before
    assert count(db, InterMatterJournal) == 0
    transfers.create_inter_matter_journal(db, payload=payload, user=user); db.commit()
    assert balance(db, first) == 6000 and balance(db, second) == 4000


def test_selected_bank_funds_cannot_borrow_from_other_bank():
    db, user, first, second = fixture()
    def bank(name): return create_bank_account(db, name=name, account_kind='client', sort_code=None,
        account_number=None, is_default=False, is_active=True)
    a, b = bank('A'), bank('B')
    post(db, user, first, firm_bank_account_id=a.id, payment_method='bacs'); db.commit()
    with pytest.raises(HTTPException) as error:
        transfers.create_inter_matter_journal(db, payload=transfer_payload(first, second, firm_bank_account_id=b.id), user=user)
    assert error.value.status_code == 422
    db.rollback()
    pending = post(db, user, first, direction='debit', firm_bank_account_id=b.id,
        anticipated=True, anticipated_for_date=date.today())
    db.commit()
    with pytest.raises(HTTPException) as error: approve_ledger_pair(first.id, pending.pair_id, user, db)
    assert error.value.status_code == 422
    assert balance(db, first) == 10000 and balance(db, second) == 0


def test_posting_reversal_is_compensating_once_and_not_a_new_receipt():
    db, user, first, _ = fixture()
    original = post(db, user, first); db.commit()
    payload = reversal()
    result = operations.reverse_posting(db, case_id=first.id, pair_id=original.pair_id, payload=payload, user=user)
    db.commit()
    assert operations.reverse_posting(db, case_id=first.id, pair_id=original.pair_id, payload=payload, user=user) == result
    assert balance(db, first) == 0 and count(db, LedgerEntry) == 2
    for pair in (original.pair_id, uuid.UUID(result['pair_id'])):
        with pytest.raises(HTTPException): require_external_receipt(db, pair)
        with pytest.raises(HTTPException): operations.reverse_posting(db, case_id=first.id, pair_id=pair,
                                                                      payload=reversal(), user=user)


def test_transfer_reversal_is_whole_atomic_and_retry_safe(monkeypatch):
    db, user, first, second = fixture()
    post(db, user, first)
    journal = transfers.create_inter_matter_journal(db, payload=transfer_payload(first, second), user=user)
    db.commit()
    with pytest.raises(HTTPException): operations.reverse_posting(db, case_id=first.id, pair_id=journal.from_pair_id,
                                                                  payload=reversal(), user=user)
    with pytest.raises(HTTPException): require_external_receipt(db, journal.to_pair_id)
    payload = reversal()
    with monkeypatch.context() as patch:
        patch.setattr(transfers, 'log_event', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('audit failure')))
        with pytest.raises(RuntimeError): transfers.reverse_inter_matter_journal(db, journal_id=journal.id, payload=payload, user=user)
        db.rollback()
    assert balance(db, first) == 6000 and balance(db, second) == 4000
    result = transfers.reverse_inter_matter_journal(db, journal_id=journal.id, payload=payload, user=user); db.commit()
    assert transfers.reverse_inter_matter_journal(db, journal_id=journal.id, payload=payload, user=user).id == result.id
    assert balance(db, first) == 10000 and balance(db, second) == 0
    for jid in (journal.id, result.id):
        with pytest.raises(HTTPException): transfers.reverse_inter_matter_journal(db, journal_id=jid, payload=reversal(), user=user)


def test_spent_transfer_cannot_be_reversed():
    db, user, first, second = fixture()
    post(db, user, first)
    journal = transfers.create_inter_matter_journal(db, payload=transfer_payload(first, second), user=user)
    post(db, user, second, 2000, 'debit'); db.commit()
    with pytest.raises(HTTPException) as error:
        transfers.reverse_inter_matter_journal(db, journal_id=journal.id, payload=reversal(), user=user)
    assert error.value.status_code == 422
    assert count(db, InterMatterJournal) == 1


@pytest.mark.parametrize('operation', ['post', 'reverse'])
def test_posting_and_reversal_audit_failure_roll_back(operation, monkeypatch):
    db, user, first, _ = fixture()
    original = post(db, user, first); db.commit()
    before = (count(db, LedgerEntry), count(db, LedgerOperation), count(db, AuditEvent))
    with monkeypatch.context() as patch:
        def fail(*a, **kw): raise RuntimeError('Audit storage unavailable')
        patch.setattr(operations, 'log_ledger_post' if operation == 'post' else 'log_event', fail)
        with pytest.raises(RuntimeError):
            if operation == 'post': post(db, user, first)
            else: operations.reverse_posting(db, case_id=first.id, pair_id=original.pair_id, payload=reversal(), user=user)
        db.rollback()
    assert (count(db, LedgerEntry), count(db, LedgerOperation), count(db, AuditEvent)) == before
    assert balance(db, first) == 10000


def test_allocations_and_reversals_exclude_each_other():
    from tests.test_invoice_allocation import allocation_fixture, allocate
    db, user, first, invoice, pair = allocation_fixture()
    allocate(db, user, invoice, pair); db.commit()
    with pytest.raises(HTTPException, match='allocations'):
        operations.reverse_posting(db, case_id=first.id, pair_id=pair, payload=reversal(), user=user)
    db.rollback()
    # An unallocated receipt can be reversed, but neither original nor compensation is a new receipt.
    receipt = operations.post_ledger_operation(first.id, LedgerPostCreate(description='Other receipt', amount_pence=10000,
        office_direction='credit', idempotency_key=uuid.uuid4()), user, db)
    result = operations.reverse_posting(db, case_id=first.id, pair_id=receipt.pair_id, payload=reversal(), user=user)
    db.commit()
    for candidate in (receipt.pair_id, uuid.UUID(result['pair_id'])):
        with pytest.raises(HTTPException): allocate(db, user, invoice, candidate, 1000)


def test_matching_and_reversals_exclude_each_other_and_preserve_original_bank():
    from tests.test_bank_integrity import fixture as bank_fixture, match
    from app.bank_matching_service import unmatch_line
    db, user, first, bank, _, _, line, leg = bank_fixture()
    match(db, user, line, leg); db.commit()
    with pytest.raises(HTTPException, match='Unmatch'):
        operations.reverse_posting(db, case_id=first.id, pair_id=leg.pair_id, payload=reversal(), user=user)
    db.rollback()
    unmatch_line(db, line_id=line.id, actor=user, expected_version=1)
    result = operations.reverse_posting(db, case_id=first.id, pair_id=leg.pair_id, payload=reversal(), user=user)
    db.commit()
    compensation = db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id == uuid.UUID(result['pair_id'])))
    assert compensation.firm_bank_account_id == bank.id and not bank.is_active
    with pytest.raises(HTTPException): match(db, user, line, leg)


def test_replay_after_reversal_does_not_recreate_money_and_rechecks_permissions():
    db, _, first, _ = fixture()
    category = add_cashier_category(db)
    user = add_user(db, role=UserRole.user, permission_category_id=category.id)
    payload = LedgerPostCreate(description='Receipt', amount_pence=10000, client_direction='credit', idempotency_key=uuid.uuid4())
    result = operations.post_ledger_operation(first.id, payload, user, db)
    undo = reversal()
    operations.reverse_posting(db, case_id=first.id, pair_id=result.pair_id, payload=undo, user=user); db.commit()
    assert operations.post_ledger_operation(first.id, payload, user, db) == result
    assert balance(db, first) == 0
    category.perm_post_client = False
    db.commit()
    with pytest.raises(HTTPException) as error: operations.post_ledger_operation(first.id, payload, user, db)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        operations.reverse_posting(db, case_id=first.id, pair_id=result.pair_id, payload=undo, user=user)
    assert error.value.status_code == 403


def test_closed_period_blocks_post_approval_and_reversal():
    from app.models import BankReconciliation
    from app.timeutil import utcnow
    db, user, first, _ = fixture()
    bank = create_bank_account(db, name='Closed period bank', account_kind='client', sort_code=None,
        account_number=None, is_default=False, is_active=True)
    original = post(db, user, first, firm_bank_account_id=bank.id, payment_method='bacs')
    pending = post(db, user, first, amount=100, firm_bank_account_id=bank.id, anticipated=True, anticipated_for_date=date.today())
    db.add(BankReconciliation(firm_bank_account_id=bank.id, period_end_date=utcnow().date(), status='approved',
        statement_balance_pence=10000, ledger_total_pence=10000, unpresented_total_pence=0,
        unmatched_statement_total_pence=0, difference_pence=0, prepared_by_user_id=user.id))
    db.commit()
    for action in ('post', 'approve', 'reverse'):
        with pytest.raises(HTTPException) as error:
            if action == 'post': post(db, user, first, firm_bank_account_id=bank.id, payment_method='bacs')
            elif action == 'approve': approve_ledger_pair(first.id, pending.pair_id, user, db)
            else: operations.reverse_posting(db, case_id=first.id, pair_id=original.pair_id, payload=reversal(), user=user)
        assert error.value.status_code == 409
        db.rollback()
    assert balance(db, first) == 10000
