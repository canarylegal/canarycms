import uuid
from datetime import date
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import (User,UserPermissionCategory,Case,CaseLockMode,CaseTimeEntry,CaseTimeEntryStatus,
    CaseInvoice,CaseInvoiceLine,InvoiceSeq,LedgerEntry)
from app.invoice_service import create_case_invoice
from app.schemas import CaseInvoiceCreate
from tests.test_permission_boundaries_postgres import sample


def setup_invoice(s,permission=None,open_case=True):
    with SessionLocal() as db:
        user=db.get(User,uuid.UUID(s['staff']))
        category=db.get(UserPermissionCategory,user.permission_category_id)
        if permission:setattr(category,permission,True)
        if open_case:db.get(Case,uuid.UUID(s['case'])).lock_mode=CaseLockMode.none
        db.get(User,uuid.UUID(s['admin'])).charge_rate_pence_per_hour=10000
        row=CaseTimeEntry(case_id=uuid.UUID(s['case']),user_id=uuid.UUID(s['admin']),created_by_user_id=uuid.UUID(s['admin']),work_date=date.today(),duration_minutes=60,description='Other fee earner time',status=CaseTimeEntryStatus.unbilled)
        db.add(row);db.commit()
        return {'credit_user_id':s['admin'],'lines':[],'time_entry_ids':[str(row.id)]}


def billing_snapshot():
    with SessionLocal() as db:
        return {m.__tablename__:sorted(repr(tuple(row)) for row in db.execute(select(m.__table__)))
            for m in (CaseInvoice,CaseInvoiceLine,InvoiceSeq,LedgerEntry,CaseTimeEntry)}

@pytest.mark.parametrize('permission',[None,'perm_fee_earner','perm_post_client','perm_post_anticipated','perm_approve_payments'])
def test_no_billing_permission_cannot_reserve_other_staff_time(sample,permission):
    s=sample;payload=setup_invoice(s,permission);before=billing_snapshot()
    with TestClient(app) as client:
        result=client.post('/cases/'+s['case']+'/invoices',json=payload,headers=s['headers'])
        assert result.status_code==403,result.text
    assert billing_snapshot()==before

@pytest.mark.parametrize('permission',['perm_post_office','perm_approve_invoices'])
def test_billing_staff_can_create_pending_invoice_but_approval_is_separate(sample,permission):
    s=sample;payload=setup_invoice(s,permission)
    with TestClient(app) as client:
        result=client.post('/cases/'+s['case']+'/invoices',json=payload,headers=s['headers'])
        assert result.status_code==201,result.text
        assert result.json()['status']=='pending_approval'
        if permission=='perm_post_office':
            assert client.post('/cases/'+s['case']+'/invoices/'+result.json()['id']+'/approve',headers=s['headers']).status_code==403
    with SessionLocal() as db:
        assert db.get(CaseTimeEntry,uuid.UUID(payload['time_entry_ids'][0])).status==CaseTimeEntryStatus.billed
        assert not any(db.scalars(select(LedgerEntry.is_approved).where(LedgerEntry.pair_id==uuid.UUID(result.json()['ledger_pair_id']))))


def test_billing_permission_does_not_override_matter_access(sample):
    s=sample;payload=setup_invoice(s,'perm_post_office',open_case=False);before=billing_snapshot()
    with TestClient(app) as client:assert client.post('/cases/'+s['case']+'/invoices',json=payload,headers=s['headers']).status_code==403
    assert billing_snapshot()==before


def test_service_rechecks_revoked_billing_permission_with_cached_actor(sample):
    s=sample;payload=setup_invoice(s,'perm_post_office')
    with SessionLocal() as db:
        actor=db.get(User,uuid.UUID(s['staff']));category=db.get(UserPermissionCategory,actor.permission_category_id)
        with SessionLocal() as revoke:
            revoke.get(UserPermissionCategory,category.id).perm_post_office=False;revoke.commit()
        before=billing_snapshot()
        with pytest.raises(HTTPException) as error:create_case_invoice(uuid.UUID(s['case']),CaseInvoiceCreate(**payload),actor,db)
        assert error.value.status_code==403;db.rollback()
    assert billing_snapshot()==before

@pytest.mark.parametrize('path',['/docs','/redoc','/openapi.json'])
def test_api_docs_require_admin_session(sample,path):
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        assert client.get(path,headers=sample['headers']).status_code==403
        response=client.get(path,headers=sample['admin_headers'])
        assert response.status_code==200,response.text
        assert response.headers['cache-control']=='private, no-store'
        if path=='/openapi.json':assert '/cases/{case_id}/invoices' in response.json()['paths']
        else:assert './openapi.json' in response.text
