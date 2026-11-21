"""Read-only diagnostics distinguish damaged records from legitimate accounting differences."""
import json
import uuid
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import select,event
from app.financial_validation import validate_financial_data
from app.models import (CaseInvoiceLine,LedgerEntry,CaseInvoiceAllocation,InvoiceAllocationReversal,
    BankReconciliation,AuditEvent)
from app.ledger_service import post_transaction
from app.schemas import LedgerPostCreate
from tests.test_invoice_allocation import allocation_fixture,allocate


def fixture(db=None):
    db,user,case,inv,pair=allocation_fixture(db)
    db.add(CaseInvoiceLine(invoice_id=inv.id,line_type='fee',description='Private client description',amount_pence=10000,tax_pence=0))
    charge=post_transaction(case.id,LedgerPostCreate(description='Invoice charge',amount_pence=10000,office_direction='debit'),user,db)
    inv.ledger_pair_id=charge.pair_id
    db.commit()
    return db,user,case,inv,pair


def codes(report,severity='error'):
    return {f['code'] for f in report['findings'] if f['severity']==severity}


def test_valid_difference_between_cash_debt_and_billing_is_explained_not_flagged():
    db,_,_,_,_=fixture()
    report=validate_financial_data(db)
    assert report['status']=='clear'
    bridge=report['reconciliation']
    assert bridge['office_balance_pence']==0
    assert bridge['invoice_linked_office_pence']==-10000
    assert bridge['other_office_postings_pence']==10000
    assert bridge['outstanding_invoice_pence']==10000
    assert 'Private client description' not in json.dumps(report)
    db.close()


@pytest.mark.parametrize('damage,expected',[
    ('lines','invoice_line_total_mismatch'),('charge','invoice_posting_mismatch'),
    ('cache','allocation_cached_total_mismatch'),('paid','allocation_paid_status_mismatch'),
    ('negative','nonpositive_posting'),('shape','invalid_posting_shape'),
])
def test_invoice_and_posting_inconsistencies_are_reported(damage,expected):
    db,_,_,inv,pair=fixture()
    leg=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==inv.ledger_pair_id))
    if damage=='lines': db.scalar(select(CaseInvoiceLine)).amount_pence=1
    elif damage=='charge': leg.amount_pence=1
    elif damage=='cache': inv.amount_allocated_pence=42
    elif damage=='paid': inv.paid_at=datetime.now(timezone.utc)
    elif damage=='negative': leg.amount_pence=-1
    elif damage=='shape':
        db.add(LedgerEntry(account_id=leg.account_id,pair_id=leg.pair_id,direction=leg.direction,
            amount_pence=leg.amount_pence,description='Duplicate office leg',is_approved=True))
    db.commit()
    assert expected in codes(validate_financial_data(db))
    db.close()


def test_historical_reversed_allocations_still_have_chronology_checks():
    db,user,_,inv,pair=fixture()
    allocation=allocate(db,user,inv,pair,4000)
    db.flush()
    db.add(InvoiceAllocationReversal(allocation_id=allocation.id,actor_user_id=user.id,
        idempotency_key=uuid.uuid4(),reason='Historical correction',
        reversed_at=allocation.allocated_at-timedelta(days=1)))
    inv.amount_allocated_pence=0;db.commit()
    assert 'reversal_before_allocation' in codes(validate_financial_data(db))
    db.close()


def test_legacy_evidence_gap_is_review_not_proof_of_bad_money():
    db,_,_,_,pair=fixture()
    leg=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==pair));leg.recognised_at=None;db.commit()
    report=validate_financial_data(db)
    assert report['status']=='review_required' and not codes(report)
    assert codes(report,'review')=={'missing_approval_evidence'}
    db.add(AuditEvent(action='ledger.post',entity_type='ledger_pair',entity_id=str(pair),meta_json='{"is_approved":true}'))
    db.commit()
    assert validate_financial_data(db)['status']=='clear'
    assert leg.recognised_at is None  # Evidence is not silently written back.
    db.close()


def test_legacy_bank_match_with_missing_bank_tag_requires_review():
    from tests.test_bank_integrity import fixture as bank_fixture
    db,user,case,bank,account,imp,line,leg=bank_fixture()
    leg.recognised_at=leg.posted_at
    line.matched_pair_id=leg.pair_id
    leg.firm_bank_account_id=None
    db.commit()
    report=validate_financial_data(db)
    finding=next(f for f in report['findings'] if f['code']=='invalid_bank_match')
    assert finding['evidence']['reasons']==['bank_account_mismatch']
    assert line.matched_pair_id==leg.pair_id and leg.firm_bank_account_id is None
    db.close()


def test_saved_reconciliation_checks_its_own_arithmetic_not_todays_balance():
    from tests.test_bank_integrity import fixture as bank_fixture,PERIOD
    db,user,case,bank,account,imp,line,leg=bank_fixture()
    row=BankReconciliation(firm_bank_account_id=bank.id,period_end_date=PERIOD,
        statement_balance_pence=5000,ledger_total_pence=4000,unpresented_total_pence=100,
        unmatched_statement_total_pence=200,difference_pence=900,prepared_by_user_id=user.id)
    db.add(row);db.commit()
    assert 'saved_bank_reconciliation_arithmetic' not in codes(validate_financial_data(db))
    row.difference_pence=0;db.commit()
    assert 'saved_bank_reconciliation_arithmetic' in codes(validate_financial_data(db))
    db.close()


def test_diagnostics_issue_selects_only_and_are_deterministic():
    db,_,_,_,_=fixture()
    statements=[]
    def observe(conn,cursor,statement,params,context,many):statements.append(statement)
    event.listen(db.bind,'before_cursor_execute',observe)
    first=validate_financial_data(db);second=validate_financial_data(db)
    assert first==second and all(s.lstrip().upper().startswith('SELECT') for s in statements)
    assert not db.new and not db.dirty and not db.deleted
    db.close()


def test_restored_bank_match_to_deleted_posting_is_reported_without_unmatching():
    from tests.test_bank_integrity import fixture as bank_fixture
    db,_,_,_,_,_,line,leg=bank_fixture()
    pair=leg.pair_id
    line.matched_pair_id=pair;db.delete(leg);db.commit()
    report=validate_financial_data(db)
    finding=next(f for f in report['findings'] if f['code']=='invalid_bank_match')
    assert finding['evidence']['reasons']==['requires_one_client_leg']
    assert line.matched_pair_id==pair
    db.close()


def test_transfer_posting_damage_is_detected():
    from tests.test_ledger_operations import fixture as transfer_fixture,post,transfer_payload
    from app import inter_matter_journal_service as transfers
    db,user,first,second=transfer_fixture()
    post(db,user,first)
    transfers.create_inter_matter_journal(db,payload=transfer_payload(first,second),user=user)
    db.commit()
    assert not codes(validate_financial_data(db))
    from app.models import InterMatterJournal
    stored=db.scalar(select(InterMatterJournal))
    leg=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==stored.to_pair_id));leg.amount_pence+=1;db.commit()
    assert 'transfer_posting_mismatch' in codes(validate_financial_data(db))
    db.close()


def test_compensating_posting_must_preserve_amount_and_bank():
    from tests.test_ledger_operations import fixture as ledger_fixture,post,reversal
    from app.ledger_operations import reverse_posting
    db,user,first,_=ledger_fixture()
    result=post(db,user,first)
    result=reverse_posting(db,case_id=first.id,pair_id=result.pair_id,user=user,payload=reversal())
    db.commit()
    assert not codes(validate_financial_data(db))
    leg=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==uuid.UUID(result['pair_id'])))
    leg.amount_pence+=1;db.commit()
    assert 'posting_reversal_mismatch' in codes(validate_financial_data(db))
    assert 'negative_client_matter_balance' in codes(validate_financial_data(db))
    db.close()


@pytest.mark.parametrize('status,exit_code',[('clear',0),('errors',1),('review_required',2)])
def test_operator_exit_status_and_json(monkeypatch,capsys,status,exit_code):
    from scripts import check_financial_data as cli
    class FakeSession:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get_bind(self):
            from types import SimpleNamespace
            return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        def rollback(self):pass
    monkeypatch.setattr(cli,'SessionLocal',FakeSession)
    monkeypatch.setattr(cli,'begin_report_snapshot',lambda db:None)
    monkeypatch.setattr(cli,'validate_financial_data',lambda db:{'status':status})
    assert cli.main()==exit_code
    assert json.loads(capsys.readouterr().out)=={'status':status}


def test_failed_audit_does_not_print_a_partial_clean_report(monkeypatch,capsys):
    from scripts import check_financial_data as cli
    def fail():raise RuntimeError('private database information')
    monkeypatch.setattr(cli,'SessionLocal',fail)
    assert cli.main()==3
    captured=capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err)=={'status':'execution_failed','error_type':'RuntimeError'}
