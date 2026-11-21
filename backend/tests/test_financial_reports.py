"""Independent historical financial expectations and JSON/XLSX/pack parity."""
import asyncio
from datetime import date, datetime, timezone
from io import BytesIO
import uuid
import zipfile

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from app.models import (CaseInvoiceLine, CaseInvoiceAllocation, InvoiceAllocationReversal,
                        LedgerEntry, CaseStatus, FirmSettings)
from app.reports_service import (report_aged_debt, report_client_office_balances,
    report_billing, report_ledger_leg_activity)
from app.reconciliation_service import firm_wide_ledger_totals
from app.models import LedgerAccountType
from tests.test_invoice_allocation import allocation_fixture


def dt(day, hour=0):
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def history(db=None):
    db, user, case, inv, pair = allocation_fixture(db)
    case.created_at = dt(1)
    inv.created_at = dt(1)
    inv.approved_at = dt(2)
    # The receipt was entered on 3 Jan, but only recognised on 4 Jan.
    for leg in db.scalars(select(LedgerEntry).where(LedgerEntry.pair_id == pair)):
        leg.posted_at = dt(3)
        leg.recognised_at = dt(4)
    allocation = CaseInvoiceAllocation(invoice_id=inv.id, ledger_pair_id=pair,
        amount_pence=6000, allocated_by_user_id=user.id, allocated_at=dt(5))
    db.add(allocation); db.flush()
    db.add(InvoiceAllocationReversal(allocation_id=allocation.id, actor_user_id=user.id,
        idempotency_key=uuid.uuid4(), reason='Correct historical payment', reversed_at=dt(7)))
    inv.status = 'voided'; inv.voided_at = dt(9)
    inv.amount_allocated_pence = 0
    db.add(CaseInvoiceLine(invoice_id=inv.id, line_type='fee', description='Fee', amount_pence=8000, tax_pence=1600))
    db.add(CaseInvoiceLine(invoice_id=inv.id, line_type='disbursement', description='Cost', amount_pence=400, tax_pence=0))
    db.commit()
    return db, user, case, inv


@pytest.mark.parametrize('day,expected', [(1,0),(2,10000),(4,10000),(5,4000),(6,4000),(7,10000),(8,10000),(9,0)])
def test_debt_uses_approval_allocation_correction_and_void_cutoffs(day, expected):
    db, user, _, _ = history()
    rows, buckets = report_aged_debt([user.id], db, as_of=date(2026,1,day))
    assert sum(r.invoice_total_pence for r in rows) == expected
    assert sum(buckets.values()) == expected
    # Positive office credit must not erase outstanding invoice principal.
    if rows and day >= 4: assert rows[0].office_balance_pence == 10000
    db.close()


def test_later_full_payment_does_not_erase_earlier_debt_and_ignores_cache():
    db, user, case, inv = history()
    inv.status='approved'; inv.voided_at=None; inv.paid_at=dt(10); inv.amount_allocated_pence=10000
    pair = db.scalar(select(CaseInvoiceAllocation.ledger_pair_id))
    db.add(CaseInvoiceAllocation(invoice_id=inv.id, ledger_pair_id=pair, amount_pence=10000,
        allocated_by_user_id=user.id, allocated_at=dt(10)))
    db.commit()
    assert sum(report_aged_debt([user.id], db, as_of=date(2026,1,8))[1].values()) == 10000
    assert sum(report_aged_debt([user.id], db, as_of=date(2026,1,10))[1].values()) == 0
    db.close()


def test_balances_include_closed_matters_and_agree_with_ledger_and_reconciliation():
    db, user, case, _ = history()
    case.status = CaseStatus.closed; db.commit()
    for day, expected in [(3,0),(4,10000)]:
        end = date(2026,1,day)
        rows, totals = report_client_office_balances([user.id], db, as_of=end)
        assert len(rows) == 1 and totals['office_balance_pence'] == expected
        assert firm_wide_ledger_totals(db, end) == (0,expected)
        legs = report_ledger_leg_activity([user.id],db,account_type=LedgerAccountType.office,
            date_to=end,approved_only=True)
        assert sum(r.amount_pence if r.direction=='credit' else -r.amount_pence for r in legs) == expected
    leg = db.scalar(select(LedgerEntry)); leg.is_anticipated=True; db.commit()
    assert report_client_office_balances([user.id], db)[1]['office_balance_pence'] == 0
    db.close()


def test_billing_register_reconstructs_status_before_approval_and_void():
    db,user,_,_ = history()
    for day,status,amount in [(1,'pending_approval',10000),(2,'approved',10000),(8,'approved',10000),(9,None,0)]:
        rows, totals = report_billing([user.id],db,date_to=date(2026,1,day))
        assert sum(totals.values()) == amount
        assert [r.invoice_status for r in rows] == ([status] if status else [])
    db.close()


async def response_bytes(response):
    return b''.join([chunk async for chunk in response.body_iterator])


def test_json_xlsx_and_accountant_pack_have_same_historical_amounts(monkeypatch):
    from app.routers import reports
    from app.schemas import AgedDebtReportIn
    from app.accountant_pack_service import build_accountant_pack
    db,user,case,inv = history()
    # Permission behaviour is tested separately; this fixture's category is cashier-only.
    monkeypatch.setattr(reports,'enforce_fee_earner_ids',lambda u,d,ids:ids)
    body = AgedDebtReportIn(fee_earner_user_ids=[user.id],as_of=date(2026,1,6))
    result = reports.post_aged_debt_report(body,user,db,format='json')
    response = reports.post_aged_debt_report(body,user,db,format='xlsx')
    wb = load_workbook(BytesIO(asyncio.run(response_bytes(response))),data_only=True)
    assert result['rows'][0]['invoice_total_pence'] == 4000
    assert wb.active.cell(2,9).value == 40
    pack=build_accountant_pack(db,fee_earner_user_ids=[user.id],period_end_date=body.as_of,
        date_from=None,date_to=None,include_balances=True,include_billing=True,
        include_ledger_activity=True,include_aged_debt=True,include_exceptions=False,
        include_reconcile_doc=False,large_posting_min_pence=500000,generated_by_name='Test')
    with zipfile.ZipFile(BytesIO(pack.zip_bytes)) as z:
        packed=load_workbook(BytesIO(z.read(next(n for n in z.namelist() if n.endswith('.xlsx')))),data_only=True)
    assert packed['Client office balances'].cell(2,6).value == 100
    aged=next(s for s in packed if 'aged' in s.title.lower())
    assert aged.cell(2,9).value == 40
    assert not db.new and not db.dirty
    db.close()


def test_delayed_approval_records_recognition_without_changing_original_date(monkeypatch):
    from app import ledger_service
    from app.schemas import LedgerPostCreate
    db,user,case,_ = history()
    monkeypatch.setattr(ledger_service,'utcnow',lambda:dt(11))
    result=ledger_service.post_transaction(case.id,LedgerPostCreate(description='Pending credit',
        amount_pence=2500,office_direction='credit'),user,db,force_unapproved=True)
    db.commit()
    leg=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==result.pair_id))
    assert leg.recognised_at is None
    monkeypatch.setattr(ledger_service,'utcnow',lambda:dt(13))
    ledger_service.approve_ledger_pair(case.id,result.pair_id,user,db)
    db.commit(); db.refresh(leg)
    assert leg.posted_at.date() == date(2026,1,11)
    assert leg.recognised_at.date() == date(2026,1,13)
    assert firm_wide_ledger_totals(db,date(2026,1,12)) == (0,10000)
    assert firm_wide_ledger_totals(db,date(2026,1,13)) == (0,12500)
    db.close()


def test_request_snapshot_starts_before_authentication_queries(monkeypatch):
    from app import db as database
    from starlette.requests import Request
    calls=[]
    class FakeSession:
        def commit(self): calls.append('commit')
        def close(self): calls.append('close')
    monkeypatch.setattr(database,'SessionLocal',FakeSession)
    monkeypatch.setattr(database,'begin_report_snapshot',lambda db:calls.append('snapshot'))
    request=Request({'type':'http','path':'/reports/aged-debt','headers':[],'query_string':b''})
    generator=database.get_db(request)
    next(generator)
    assert calls == ['snapshot']
    with pytest.raises(StopIteration): next(generator)
    assert calls == ['snapshot','commit','close']


@pytest.mark.parametrize('days,bucket',[(30,'0-30'),(31,'31-60'),(60,'31-60'),(61,'61-90'),(90,'61-90'),(91,'90+')])
def test_age_bucket_boundaries(days,bucket):
    from datetime import timedelta
    db,user,_,inv=history()
    inv.status='approved'; inv.voided_at=None; db.commit()
    rows,totals=report_aged_debt([user.id],db,as_of=date(2026,1,2)+timedelta(days=days))
    assert rows[0].age_days == days and rows[0].age_bucket == bucket
    assert totals[bucket] == 10000 and sum(totals.values()) == 10000
    db.close()


def test_bank_and_firm_totals_share_delayed_recognition_cutoff():
    from tests.test_bank_integrity import fixture, totals, PERIOD
    db,user,case,bank,account,_,_,leg=fixture()
    leg.recognised_at=datetime(2026,2,1,tzinfo=timezone.utc); db.commit()
    result=totals(db,bank)
    assert result['ledger_total_pence'] == 0
    assert firm_wide_ledger_totals(db,PERIOD)[0] == 0
    db.close()


def test_unknown_legacy_invoice_approval_fails_historical_report_explicitly():
    from fastapi import HTTPException
    db,user,_,inv=history()
    inv.status='approved'; inv.approved_at=None; inv.voided_at=None; db.commit()
    with pytest.raises(HTTPException) as error:
        report_aged_debt([user.id],db,as_of=date(2026,1,8))
    assert error.value.status_code == 409 and 'approval timestamp' in error.value.detail
    assert sum(report_aged_debt([user.id],db)[1].values()) == 10000
    db.close()


def test_snapshot_scope_excludes_reconciliation_mutations_and_covers_renderers():
    from app.db import REPORT_SNAPSHOT_PATHS
    from app.routers.reports import router
    assert {route.path for route in router.routes} == REPORT_SNAPSHOT_PATHS
    assert '/reports/reconciliations' not in REPORT_SNAPSHOT_PATHS
    assert '/reports/reconciliations/id/approve' not in REPORT_SNAPSHOT_PATHS


def test_invoice_and_ledger_share_the_same_approval_and_void_instant(monkeypatch):
    from app import ledger_service
    from app.invoice_service import create_case_invoice,approve_case_invoice,void_case_invoice
    from tests.test_invoice_service import _invoice_payload
    from tests.ledger_test_helpers import ledger_test_session,add_user,add_case
    db=ledger_test_session(); user=add_user(db); case=add_case(db,fee_earner_user_id=user.id)
    inv=create_case_invoice(case.id,_invoice_payload(credit_user_id=user.id),user,db)
    from app.models import CaseInvoice
    inv=db.get(CaseInvoice,inv.id)
    inv.created_at=dt(1); db.flush()
    monkeypatch.setattr(ledger_service,'utcnow',lambda:dt(2))
    approve_case_invoice(case.id,inv.id,user,db); db.commit()
    assert inv.approved_at.date()==date(2026,1,2)
    leg=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==inv.ledger_pair_id))
    assert inv.approved_at==leg.recognised_at
    monkeypatch.setattr(ledger_service,'utcnow',lambda:dt(3))
    void_case_invoice(case.id,inv.id,user,db); db.commit()
    reversal=db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id==inv.reversal_pair_id))
    assert inv.voided_at==reversal.recognised_at and inv.voided_at.date()==date(2026,1,3)
    db.close()
