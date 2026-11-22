"""Every shared-card write must honor all affected matters, including history."""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete, text
from sqlalchemy.exc import DBAPIError
from app.main import app
from app.db import SessionLocal
from app.models import Contact, CaseContact, ContactType, User, CaseAccessRule, PortalActivityEvent
from app.contact_merge_permissions import require_contact_mutation_access
from tests.test_permission_boundaries_postgres import sample, allow_staff
from tests.test_staff_contact_merge import prepare, snapshot, KINDS
from tests.ledger_test_helpers import add_case


def local_link(s):
    with SessionLocal() as db:
        case=add_case(db,fee_earner_user_id=uuid.UUID(s['staff']))
        row=CaseContact(case_id=case.id,contact_id=uuid.UUID(s['contact']),type=ContactType.person,name='Local snapshot')
        db.add(row);db.commit()
        return str(case.id),str(row.id)


def patch(client,s,route,local,*,push=True):
    case_id,row_id=local
    path='/contacts/'+s['contact'] if route=='direct' else f'/cases/{case_id}/contacts/{row_id}'
    payload={'name':'Permitted new name','address_line1':'Synthetic new address'}
    if route=='matter':payload['push_to_global']=push
    return client.patch(path,json=payload,headers=s['headers'])

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('route',['direct','matter'])
def test_shared_write_denied_without_changes(sample,kind,route):
    s=sample;prepare(s,kind,'source');local=local_link(s);before=snapshot()
    with TestClient(app) as client:
        result=patch(client,s,route,local)
        assert result.status_code==403,result.text
        assert s['case'] not in result.text
    assert snapshot()==before

@pytest.mark.parametrize('kind',KINDS)
@pytest.mark.parametrize('route',['direct','matter'])
def test_staff_with_every_matter_can_write_shared_card(sample,kind,route):
    s=sample;prepare(s,kind,'source');local=local_link(s);allow_staff(s)
    with TestClient(app) as client:
        result=patch(client,s,route,local)
        assert result.status_code==200,result.text
    with SessionLocal() as db:
        contact=db.get(Contact,uuid.UUID(s['contact']))
        assert contact.name=='Permitted new name'
        assert contact.address_line1=='Synthetic new address'


def test_local_snapshot_edit_does_not_need_other_matter_access(sample):
    s=sample;local=local_link(s)
    with SessionLocal() as db:original=db.get(Contact,uuid.UUID(s['contact'])).name
    with TestClient(app) as client:assert patch(client,s,'matter',local,push=False).status_code==200
    with SessionLocal() as db:
        assert db.get(Contact,uuid.UUID(s['contact'])).name==original
        assert db.get(CaseContact,uuid.UUID(local[1])).name=='Permitted new name'


def test_unlinked_shared_contact_remains_editable(sample):
    s=sample;prepare(s,'none','source')
    with TestClient(app) as client:assert patch(client,s,'direct',('', '')).status_code==200

@pytest.mark.parametrize('change',['reference','acl'])
def test_shared_write_locks_authorization_until_commit(sample,change):
    s=sample;allow_staff(s)
    with SessionLocal() as db:
        require_contact_mutation_access(db,db.get(User,uuid.UUID(s['staff'])),(uuid.UUID(s['contact']),))
        with SessionLocal() as other:
            other.execute(text("SET LOCAL lock_timeout = '150ms'"))
            with pytest.raises(DBAPIError) as error:
                if change=='reference':
                    other.add(PortalActivityEvent(case_id=uuid.UUID(s['case']),contact_id=uuid.UUID(s['contact']),action='test',summary='Concurrent reference'))
                    other.flush()
                else:other.execute(delete(CaseAccessRule).where(CaseAccessRule.user_id==uuid.UUID(s['staff'])))
            assert error.value.orig.sqlstate=='55P03'
            other.rollback()
        db.rollback()


def test_contact_relinked_during_authorization_fails_closed(sample,monkeypatch):
    from app import contact_merge_permissions as permissions
    s=sample;local=local_link(s);allow_staff(s)
    original=permissions.require_contact_mutation_access
    def change_then_check(db,actor,ids,**kwargs):
        with SessionLocal() as other:
            contact=Contact(type=ContactType.person,name='Concurrent replacement')
            other.add(contact);other.flush()
            other.get(CaseContact,uuid.UUID(local[1])).contact_id=contact.id
            other.commit()
        return original(db,actor,ids,**kwargs)
    monkeypatch.setattr(permissions,'require_contact_mutation_access',change_then_check)
    with TestClient(app) as client:
        response=patch(client,s,'matter',local)
        assert response.status_code==409,response.text
    with SessionLocal() as db:
        assert db.get(CaseContact,uuid.UUID(local[1])).name=='Local snapshot'
        assert db.get(Contact,uuid.UUID(s['contact'])).name!='Permitted new name'
