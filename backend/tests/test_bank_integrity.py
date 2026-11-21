"""Financial invariants and recoverable statement corrections."""
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, event

from app import bank_recon_service as service
from app.models import (AuditEvent, BankStatementImport, BankStatementLine, BankReconciliation,
    FirmBankAccount, LedgerAccount, LedgerAccountType, LedgerEntry, LedgerDirection, UserRole, CaseLockMode)
from tests.ledger_test_helpers import ledger_test_session, add_user, add_case, add_cashier_category

PERIOD = date(2026, 1, 31)


def fixture(db=None):
    db = db or ledger_test_session()
    user = add_user(db)
    matter = add_case(db, fee_earner_user_id=user.id)
    bank = FirmBankAccount(name=f'Test bank {uuid.uuid4().hex}', account_kind='client', is_active=False)
    db.add(bank); db.flush()
    account = LedgerAccount(case_id=matter.id, account_type=LedgerAccountType.client)
    db.add(account); db.flush()
    imp = BankStatementImport(firm_bank_account_id=bank.id, imported_by_user_id=user.id, line_count=1)
    db.add(imp); db.flush()
    line = new_line(db, imp)
    leg = new_leg(db, account, bank, user)
    db.commit()
    return db, user, matter, bank, account, imp, line, leg


def new_line(db, imp, amount=10000, when=PERIOD):
    line = BankStatementLine(import_id=imp.id, firm_bank_account_id=imp.firm_bank_account_id,
        statement_date=when, amount_pence=amount, description='Synthetic statement')
    db.add(line); db.flush()
    return line


def new_leg(db, account, bank, user, amount=10000, when=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)):
    leg = LedgerEntry(account_id=account.id, pair_id=uuid.uuid4(), firm_bank_account_id=bank.id,
        direction=LedgerDirection.credit if amount > 0 else LedgerDirection.debit, amount_pence=abs(amount),
        description='Synthetic posting', is_approved=True, is_anticipated=False, posted_by_user_id=user.id, posted_at=when)
    db.add(leg); db.flush()
    return leg


def match(db, user, line, leg, version=None):
    return service.match_line(db, line_id=line.id, ledger_pair_id=leg.pair_id,
        actor=user, expected_version=line.version if version is None else version)


def totals(db, bank, balance=10000):
    return service.compute_recon_totals(db, firm_bank_account_id=bank.id,
        statement_balance_pence=balance, period_end_date=PERIOD)


def test_full_dataset_and_period_boundary():
    db, user, _, bank, account, imp, line, leg = fixture()
    for _ in range(600):
        new_leg(db, account, bank, user, 100)
        new_line(db, imp, 100)
    # Newer rows must not consume a display limit before the period filter.
    for _ in range(510):
        new_leg(db, account, bank, user, 200, datetime(2026, 2, 1, tzinfo=timezone.utc))
        new_line(db, imp, 200, date(2026, 2, 1))
    result = totals(db, bank, 70000)
    assert result == dict(ledger_total_pence=70000, unpresented_total_pence=70000,
        unmatched_statement_total_pence=70000, difference_pence=0)
    assert len(service.unpresented_client_legs(db, firm_bank_account_id=bank.id, as_of=PERIOD)) == 601
    assert len(service.list_statement_lines(db, firm_bank_account_id=bank.id, import_id=imp.id, limit=None)) == 1111


@pytest.mark.parametrize('later', ['statement', 'ledger'])
def test_matching_across_period_boundary_preserves_outstanding_item(later):
    db, user, _, bank, _, _, line, leg = fixture()
    if later == 'statement': line.statement_date = date(2026, 2, 1)
    else: leg.posted_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    db.commit()
    match(db, user, line, leg)
    result = totals(db, bank, 0 if later == 'statement' else 10000)
    assert result['difference_pence'] == 0
    assert result['unpresented_total_pence'] == (10000 if later == 'statement' else 0)
    assert result['unmatched_statement_total_pence'] == (0 if later == 'statement' else 10000)


@pytest.mark.parametrize('bad', ['amount', 'direction', 'bank', 'unapproved', 'anticipated', 'office', 'two_client_legs'])
def test_ineligible_matching_has_no_effect(bad):
    db, user, _, bank, account, _, line, leg = fixture()
    if bad == 'amount': line.amount_pence += 1
    if bad == 'direction': line.amount_pence = -10000
    if bad == 'bank': leg.firm_bank_account_id = None
    if bad == 'unapproved': leg.is_approved = False
    if bad == 'anticipated': leg.is_anticipated = True
    if bad == 'office': account.account_type = LedgerAccountType.office
    if bad == 'two_client_legs':
        extra = new_leg(db, account, bank, user)
        extra.pair_id = leg.pair_id
    db.commit()
    with pytest.raises(HTTPException) as error: match(db, user, line, leg)
    assert error.value.status_code == 400
    assert line.matched_pair_id is None and line.version == 0


def test_restricted_source_matter_is_denied_to_cashier():
    db, admin, matter, _, _, _, line, leg = fixture()
    cat = add_cashier_category(db)
    user = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    matter.lock_mode = CaseLockMode.allow_list
    db.commit()
    with pytest.raises(HTTPException) as error: match(db, user, line, leg)
    assert error.value.status_code == 403


def test_duplicate_match_and_stale_correction_rejected():
    db, user, _, _, _, imp, line, leg = fixture()
    other = new_line(db, imp)
    match(db, user, line, leg)
    db.commit()
    with pytest.raises(HTTPException) as error: match(db, user, other, leg)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        service.unmatch_line(db, line_id=line.id, actor=user, expected_version=0)
    assert error.value.status_code == 409
    assert line.matched_pair_id == leg.pair_id


def test_unmatch_and_ignore_can_be_recovered_from_audit_history():
    db, user, _, bank, _, _, line, leg = fixture()
    match(db, user, line, leg)
    db.commit()
    assert totals(db, bank)['difference_pence'] == 0
    for operation in ('unmatch', 'ignore'):
        function = service.unmatch_line if operation == 'unmatch' else service.ignore_line
        function(db, line_id=line.id, actor=user, expected_version=line.version)
        db.commit()
        events = service.line_history(db, line_id=line.id, actor=user)
        event_id = next(e.id for e in events if e.action == f'bank.statement.{operation}')
        assert line.matched_pair_id is None
        service.restore_line(db, line_id=line.id, event_id=event_id, expected_version=line.version,
            actor=user, reason='Correct mistaken action')
        db.commit()
        assert line.matched_pair_id == leg.pair_id and not line.ignored
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'bank.statement.restore')) == 2


def test_restore_cannot_steal_posting_matched_elsewhere():
    db, user, _, _, _, imp, line, leg = fixture()
    match(db, user, line, leg)
    service.unmatch_line(db, line_id=line.id, actor=user, expected_version=line.version)
    correction = db.scalar(select(AuditEvent).where(AuditEvent.action == 'bank.statement.unmatch'))
    other = new_line(db, imp)
    match(db, user, other, leg)
    db.commit()
    with pytest.raises(HTTPException) as error:
        service.restore_line(db, line_id=line.id, actor=user, event_id=correction.id,
            expected_version=line.version, reason='Undo')
    assert error.value.status_code == 409
    assert line.matched_pair_id is None


@pytest.mark.parametrize('stage', ['audit', 'commit'])
def test_failed_correction_rolls_back_match_and_audit(stage, monkeypatch):
    import app.bank_matching_service as matching
    db, user, _, _, _, _, line, leg = fixture()
    match(db, user, line, leg)
    db.commit()
    def fail(*args, **kwargs): raise RuntimeError('injected failure')
    if stage == 'audit': monkeypatch.setattr(matching, 'log_event', fail)
    else: event.listen(db, 'before_commit', fail)
    with pytest.raises(RuntimeError):
        service.unmatch_line(db, line_id=line.id, actor=user, expected_version=line.version)
        db.commit()
    db.rollback()
    if stage == 'commit': event.remove(db, 'before_commit', fail)
    db.refresh(line)
    assert line.matched_pair_id == leg.pair_id and line.version == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'bank.statement.unmatch')) == 0


def test_approval_recomputes_before_checking_difference_and_reopen_preserves_snapshot():
    db, user, _, bank, _, _, line, leg = fixture()
    match(db, user, line, leg)
    row = service.create_bank_reconciliation(db, actor=user, firm_bank_account_id=bank.id,
        period_end_date=PERIOD, statement_balance_pence=10000, notes=None)
    db.commit()
    service.ignore_line(db, line_id=line.id, actor=user, expected_version=line.version)
    db.commit()
    with pytest.raises(HTTPException, match='Notes are required'):
        service.approve_bank_reconciliation(db, row=row, actor=user, expected_version=row.version)
    db.rollback()
    db.refresh(row)
    assert row.status == 'draft'
    service.refresh_bank_reconciliation(db, row, actor=user, expected_version=row.version, notes='Investigated difference')
    service.approve_bank_reconciliation(db, row=row, actor=user, expected_version=row.version)
    db.commit()
    with pytest.raises(HTTPException) as error:
        service.ignore_line(db, line_id=line.id, actor=user, expected_version=line.version, ignored=False)
    assert error.value.status_code == 409
    service.reopen_bank_reconciliation(db, row=row, actor=user, expected_version=row.version, reason='Correct ignored line')
    db.commit()
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'bank.reconciliation.reopen'))
    assert json.loads(audit.meta_json)['before']['status'] == 'approved'
    assert json.loads(audit.meta_json)['before']['difference_pence'] == 10000
    service.ignore_line(db, line_id=line.id, actor=user, expected_version=line.version, ignored=False)
    match(db, user, line, leg)
    service.approve_bank_reconciliation(db, row=row, actor=user, expected_version=row.version)
    assert row.difference_pence == 0 and row.status == 'approved'


def test_historical_invalid_match_requires_review():
    db, _, _, bank, _, _, line, leg = fixture()
    line.matched_pair_id = leg.pair_id
    line.amount_pence = 1
    db.commit()
    with pytest.raises(HTTPException, match='need review'): totals(db, bank)


def test_reports_month_end_uses_period_cutoff():
    from app.reconciliation_service import create_reconciliation
    db, user, _, bank, account, _, _, _ = fixture()
    new_leg(db, account, bank, user, 20000, datetime(2026, 2, 1, tzinfo=timezone.utc))
    row = create_reconciliation(db, actor=user, period_end_date=PERIOD,
        bank_statement_balance_pence=10000, notes=None)
    assert row.ledger_client_total_pence == 10000 and row.difference_pence == 0


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '0.001', '99999999999999'])
def test_invalid_statement_money_is_rejected(value):
    with pytest.raises(HTTPException):
        service.parse_statement_csv(f'Date,Amount\n2026-01-31,{value}\n'.encode())


def test_signed_payment_matches_and_unmatches():
    db, user, _, bank, _, _, line, leg = fixture()
    line.amount_pence = -10000
    leg.direction = LedgerDirection.debit
    db.commit()
    match(db, user, line, leg)
    assert totals(db, bank, -10000)['difference_pence'] == 0
    service.unmatch_line(db, line_id=line.id, actor=user, expected_version=1)
    assert totals(db, bank, -10000)['difference_pence'] == 0


@pytest.mark.parametrize('bad_row', ['bad-date,100', '2026-01-31,not-money'])
def test_invalid_csv_row_does_not_silently_import_a_partial_statement(bad_row):
    db, user, _, bank, _, _, _, _ = fixture()
    count = db.scalar(select(func.count()).select_from(BankStatementImport))
    with pytest.raises(HTTPException):
        service.import_statement(db, actor=user, firm_bank_account_id=bank.id, filename='test.csv',
            content=f'Date,Amount\n2026-01-31,100\n{bad_row}\n'.encode())
    assert db.scalar(select(func.count()).select_from(BankStatementImport)) == count


def test_closed_period_rejects_import_and_stale_reconciliation_edit():
    db, user, _, bank, _, _, _, _ = fixture()
    row = service.create_bank_reconciliation(db, actor=user, firm_bank_account_id=bank.id,
        period_end_date=PERIOD, statement_balance_pence=10000, notes=None)
    service.approve_bank_reconciliation(db, row=row, actor=user, expected_version=0)
    db.commit()
    with pytest.raises(HTTPException) as error:
        service.import_statement(db, actor=user, firm_bank_account_id=bank.id, filename='test.csv',
            content=b'Date,Amount\n2026-01-31,100\n')
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        service.refresh_bank_reconciliation(db, row, actor=user, expected_version=0, statement_balance_pence=0)
    assert error.value.status_code == 409
    db.rollback(); db.refresh(row)
    assert row.status == 'approved' and row.statement_balance_pence == 10000
