"""Approved cutoffs protect recognised financial events, not just tagged bank legs."""
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app import ledger_service, ledger_operations, inter_matter_journal_service as transfers
from app.accounting_periods import require_accounting_open
from app.models import (ClientAccountReconciliation, ReconciliationStatus, LedgerEntry, AuditEvent,
                        CaseInvoice, BankReconciliation, UserRole)
from app.period_reopening import preview_reopening, reopen_period
from app.schemas import LedgerPostCreate
from tests.test_ledger_operations import fixture, post, transfer_payload, reversal


def close_period(db, user, day=date(2099,1,31), *, approved=True):
    row=ClientAccountReconciliation(period_end_date=day,ledger_client_total_pence=0,
        ledger_office_total_pence=0,bank_statement_balance_pence=0,difference_pence=0,
        prepared_by_user_id=user.id,approved_by_user_id=user.id if approved else None,
        approved_at=datetime.now(timezone.utc) if approved else None,
        status=ReconciliationStatus.approved if approved else ReconciliationStatus.draft)
    db.add(row);db.commit();return row


@pytest.mark.parametrize('operation',['client','office','approve_client','approve_office','reverse_office','transfer','reverse_transfer'])
def test_all_ledger_paths_obey_firm_period(operation):
    db,user,first,second=fixture()
    post(db,user,first);db.commit()
    pending=ledger_service.post_transaction(first.id,LedgerPostCreate(description='Draft',amount_pence=100,
        **({'client_direction':'credit'} if operation=='approve_client' else {'office_direction':'credit'})),user,db,force_unapproved=True)
    office=ledger_operations.post_ledger_operation(first.id,LedgerPostCreate(description='Office',amount_pence=100,
        office_direction='credit',idempotency_key=uuid.uuid4()),user,db)
    journal=transfers.create_inter_matter_journal(db,payload=transfer_payload(first,second),user=user)
    db.commit();close_period(db,user)
    count=db.scalar(select(func.count()).select_from(LedgerEntry))
    with pytest.raises(HTTPException) as error:
        if operation in ('client','office'):
            ledger_operations.post_ledger_operation(first.id,LedgerPostCreate(description='Closed',amount_pence=100,
                **{operation+'_direction':'credit'}),user,db)
        elif operation.startswith('approve'):ledger_service.approve_ledger_pair(first.id,pending.pair_id,user,db)
        elif operation=='reverse_office':ledger_operations.reverse_posting(db,case_id=first.id,pair_id=office.pair_id,payload=reversal(),user=user)
        elif operation=='transfer':transfers.create_inter_matter_journal(db,payload=transfer_payload(first,second),user=user)
        else:transfers.reverse_inter_matter_journal(db,journal_id=journal.id,payload=reversal(),user=user)
    assert error.value.status_code==409
    db.rollback();assert db.scalar(select(func.count()).select_from(LedgerEntry))==count
    db.close()


@pytest.mark.parametrize('operation',['allocate','reverse'])
def test_invoice_allocation_events_obey_firm_period(operation):
    from tests.test_invoice_corrections import fixture as allocation_fixture, reverse
    from tests.test_invoice_allocation import allocate
    db,user,_,inv,pair,original=allocation_fixture()
    if operation=='allocate':
        reverse(db,user,inv,original);db.commit()
    close_period(db,user)
    before=inv.amount_allocated_pence
    with pytest.raises(HTTPException) as error:
        if operation=='allocate':allocate(db,user,inv,pair,1000)
        else:reverse(db,user,inv,original)
    assert error.value.status_code==409
    db.rollback();assert inv.amount_allocated_pence==before;db.close()


@pytest.mark.parametrize('operation',['create','approve','void','legacy_approve'])
def test_invoice_workflows_obey_firm_period(operation,monkeypatch):
    from app.invoice_service import create_case_invoice,approve_case_invoice,void_case_invoice
    from tests.test_invoice_service import _invoice_payload
    db,user,matter,_=fixture()
    inv=create_case_invoice(matter.id,_invoice_payload(credit_user_id=user.id),user,db)
    if operation=='void':approve_case_invoice(matter.id,inv.id,user,db)
    if operation=='legacy_approve':
        row=db.get(CaseInvoice,inv.id)
        ledger_service.approve_ledger_pair(matter.id,row.ledger_pair_id,user,db,invoice_workflow=True)
        for leg in db.scalars(select(LedgerEntry).where(LedgerEntry.pair_id==row.ledger_pair_id)):
            leg.recognised_at=datetime(2020,1,1,tzinfo=timezone.utc)
    db.commit();close_period(db,user,date(2020,1,31) if operation=='legacy_approve' else date(2099,1,31))
    with pytest.raises(HTTPException) as error:
        if operation=='create':create_case_invoice(matter.id,_invoice_payload(credit_user_id=user.id),user,db)
        elif operation in ('approve','legacy_approve'):approve_case_invoice(matter.id,inv.id,user,db)
        else:void_case_invoice(matter.id,inv.id,user,db)
    assert error.value.status_code==409
    db.rollback();db.close()


def test_exact_utc_boundary_and_shared_timestamp(monkeypatch):
    db,user,matter,_=fixture();close_period(db,user,date(2026,1,31))
    ledger_service._get_or_create_accounts(matter.id,db);db.commit()
    instants=iter([datetime(2026,1,31,23,59,59,tzinfo=timezone.utc),datetime(2026,2,1,tzinfo=timezone.utc)])
    monkeypatch.setattr(ledger_service,'utcnow',lambda:next(instants))
    payload=LedgerPostCreate(description='Boundary',amount_pence=10,office_direction='credit')
    with pytest.raises(HTTPException):ledger_service.post_transaction(matter.id,payload,user,db)
    db.rollback()
    result=ledger_service.post_transaction(matter.id,payload,user,db);db.commit()
    entry=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==result.pair_id))
    assert entry.posted_at==entry.recognised_at and entry.recognised_at.date()==date(2026,2,1)
    db.close()


def test_receipt_retries_after_closure_do_not_repost():
    db,user,matter,_=fixture()
    payload=LedgerPostCreate(description='Retry',amount_pence=100,office_direction='credit',idempotency_key=uuid.uuid4())
    result=ledger_operations.post_ledger_operation(matter.id,payload,user,db);db.commit()
    close_period(db,user)
    assert ledger_operations.post_ledger_operation(matter.id,payload,user,db)==result
    assert db.scalar(select(func.count()).select_from(LedgerEntry))==1
    db.close()


def reopen(db,user,row,preview=None):
    preview=preview or preview_reopening(db,row.id)
    return reopen_period(db,reconciliation_id=row.id,actor_id=user.id,
        expected_hash=preview['preview_hash'],reason='Reviewed financial period correction')


def test_reopening_preserves_snapshot_requires_reapproval_and_is_retry_safe():
    from app.reconciliation_service import approve_reconciliation
    db,user,_,_=fixture();row=close_period(db,user);preview=preview_reopening(db,row.id)
    assert reopen(db,user,row,preview)['status']=='reopened';db.commit()
    assert row.ledger_client_total_pence==0 and row.status==ReconciliationStatus.draft
    assert row.approved_at is None and row.approved_by_user_id is None
    audit=db.scalar(select(AuditEvent).where(AuditEvent.action=='reconciliation.reopen'))
    meta=json.loads(audit.meta_json)
    assert meta['before']['status']=='approved' and meta['review_scope']['reapproval_required']
    assert 'aged_debt' in meta['review_scope']['reports_requiring_review']
    approve_reconciliation(db,actor=user,row=row);db.commit()
    assert reopen(db,user,row,preview)['status']=='already_reopened'
    assert row.status==ReconciliationStatus.approved
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='reconciliation.reopen'))==1
    db.close()


@pytest.mark.parametrize('change',['notes','later_approval','inactive','permissions','audit_failure'])
def test_reopening_rejects_stale_unauthorised_or_failed_changes(change,monkeypatch):
    import app.period_reopening as service
    db,user,_,_=fixture();row=close_period(db,user);preview=preview_reopening(db,row.id)
    if change=='notes':row.notes='Changed review evidence';db.commit()
    if change=='later_approval':close_period(db,user,date(2099,2,28))
    if change=='inactive':user.is_active=False;db.commit()
    if change=='permissions':user.role=UserRole.user;db.commit()
    if change=='audit_failure':
        def fail(*args,**kw):raise RuntimeError('Injected failure')
        monkeypatch.setattr(service,'log_event',fail)
    with pytest.raises(RuntimeError if change=='audit_failure' else HTTPException):reopen(db,user,row,preview)
    db.rollback();assert row.status==ReconciliationStatus.approved and row.approved_at
    db.close()


def test_reopening_earlier_period_does_not_open_later_approved_cutoff():
    db,user,_,_=fixture();first=close_period(db,user,date(2026,1,31));close_period(db,user,date(2026,2,28))
    reopen(db,user,first);db.commit()
    with pytest.raises(HTTPException):require_accounting_open(db,datetime(2026,1,1,tzinfo=timezone.utc))
    db.rollback();db.close()


def test_later_approvals_voids_allocations_transfers_and_reversals_preserve_closed_reports(monkeypatch):
    from app import invoice_service, invoice_allocation_service, invoice_allocation_corrections, timeutil
    from app.reports_service import report_aged_debt,report_billing,report_client_office_balances,report_ledger_leg_activity
    from app.models import LedgerAccountType
    from tests.test_invoice_service import _invoice_payload
    from app.schemas.bank import InvoiceAllocationReversalIn
    from app.reconciliation_service import firm_wide_ledger_totals
    now=[datetime(2026,1,10,tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now[0] if tz else now[0].replace(tzinfo=None)
        @classmethod
        def utcnow(cls):return now[0].replace(tzinfo=None)
    for module in (invoice_service,invoice_allocation_service,transfers):monkeypatch.setattr(module,'datetime',Clock)
    for module in (ledger_service,ledger_operations,invoice_allocation_corrections,timeutil):monkeypatch.setattr(module,'utcnow',lambda:now[0])
    db,user,first,second=fixture()
    first.created_at=second.created_at=now[0]
    approved=invoice_service.create_case_invoice(first.id,_invoice_payload(credit_user_id=user.id),user,db)
    pending=invoice_service.create_case_invoice(first.id,_invoice_payload(credit_user_id=user.id),user,db)
    assert approved.id != pending.id  # Equal creation timestamps must not return the previous invoice.
    invoice_service.approve_case_invoice(first.id,approved.id,user,db)
    receipt=ledger_operations.post_ledger_operation(first.id,LedgerPostCreate(description='Receipt',amount_pence=12000,
        office_direction='credit',idempotency_key=uuid.uuid4()),user,db)
    client=post(db,user,first)
    allocation=invoice_allocation_service.allocate_to_invoice(db,invoice_id=approved.id,ledger_pair_id=receipt.pair_id,amount_pence=6000,actor=user)
    db.commit();cutoff=date(2026,1,31);close_period(db,user,cutoff)
    def reports():
        return (report_aged_debt([user.id],db,as_of=cutoff),report_billing([user.id],db,date_to=cutoff),
            report_client_office_balances([user.id],db,as_of=cutoff),firm_wide_ledger_totals(db,cutoff),
            report_ledger_leg_activity([user.id],db,account_type=LedgerAccountType.office,date_to=cutoff,approved_only=True))
    before=reports();assert sum(before[0][1].values())==6000
    now[0]=datetime(2026,2,2,tzinfo=timezone.utc)
    invoice_allocation_corrections.reverse_allocation(db,invoice_id=approved.id,allocation_id=allocation.id,
        payload=InvoiceAllocationReversalIn(idempotency_key=uuid.uuid4(),reason='Later correction'),actor=user)
    # Reverse receipt before invoice void so the office-balance invariant remains satisfied.
    ledger_operations.reverse_posting(db,case_id=first.id,pair_id=receipt.pair_id,payload=reversal(),user=user)
    invoice_service.void_case_invoice(first.id,approved.id,user,db)
    invoice_service.approve_case_invoice(first.id,pending.id,user,db)
    journal=transfers.create_inter_matter_journal(db,payload=transfer_payload(first,second),user=user)
    transfers.reverse_inter_matter_journal(db,journal_id=journal.id,payload=reversal(),user=user)
    ledger_operations.reverse_posting(db,case_id=first.id,pair_id=client.pair_id,payload=reversal(),user=user)
    db.commit()
    assert reports()==before
    db.close()


def test_bank_reopening_audit_identifies_affected_scope():
    from tests.test_bank_integrity import fixture as bank_fixture,PERIOD
    from app import bank_recon_service as bank
    db,user,_,account,_,_,_,_=bank_fixture()
    row=bank.create_bank_reconciliation(db,actor=user,firm_bank_account_id=account.id,period_end_date=PERIOD,
        statement_balance_pence=0,notes='Difference reviewed')
    bank.approve_bank_reconciliation(db,actor=user,row=row,expected_version=0);db.commit()
    bank.reopen_bank_reconciliation(db,actor=user,row=row,expected_version=row.version,reason='Reviewed correction');db.commit()
    ev=db.scalar(select(AuditEvent).where(AuditEvent.action=='bank.reconciliation.reopen'))
    scope=json.loads(ev.meta_json)['review_scope']
    assert scope['bank_id']==str(account.id) and scope['reapproval_required']
    db.close()


def test_failed_closure_audit_does_not_leave_a_closed_period(monkeypatch):
    from app import reconciliation_service as service
    db,user,matter,_=fixture();row=close_period(db,user,approved=False)
    def fail(*args,**kw):raise RuntimeError('Injected closure audit failure')
    with monkeypatch.context() as patch:
        patch.setattr(service,'log_event',fail)
        with pytest.raises(RuntimeError):service.approve_reconciliation(db,actor=user,row=row)
        db.rollback()
    assert row.status==ReconciliationStatus.draft
    ledger_service.post_transaction(matter.id,LedgerPostCreate(description='Open after rollback',amount_pence=1,office_direction='credit'),user,db)
    db.commit();db.close()


def test_cli_never_confirms_reopening_before_commit(capsys):
    from scripts import accounting_period_review as cli
    from unittest.mock import MagicMock,patch
    session=MagicMock();session.get_bind.return_value.dialect.name='postgresql'
    session.commit.side_effect=RuntimeError('Injected commit failure')
    manager=MagicMock();manager.__enter__.return_value=session
    with patch.object(cli,'SessionLocal',return_value=manager),patch.object(cli,'reopen_period',return_value={'status':'reopened'}):
        result=cli.main(['reopen','--reconciliation-id',str(uuid.uuid4()),'--actor-id',str(uuid.uuid4()),
            '--reviewed-hash','hash','--reason','Reviewed test'])
    out=capsys.readouterr();assert result==3 and not out.out and 'failed' in out.err


def test_historical_unmatch_preview_includes_firm_cutoff():
    from tests.test_historical_corrections import fixture as historical_fixture
    from app.historical_corrections import preview_unmatch
    db,user,_,line,_=historical_fixture();row=close_period(db,user)
    preview=preview_unmatch(db,line.id)
    assert preview['closed_firm_reconciliation_ids']==[str(row.id)]
    assert 'approved_firm_period_requires_reasoned_reopen' in preview['blockers']
    db.close()
