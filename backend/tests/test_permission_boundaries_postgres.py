"""HTTP authorization regressions with synthetic PostgreSQL fixtures."""
import os
import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import User,UserRole,UserPermissionCategory,CaseLockMode,CaseAccessRule,CaseAccessMode,Contact,ContactType,CaseContact,ContactPortalAccess,ContactPortalGrant,FirmSettings,File
from app.security import create_access_token
from app.portal_service import store_portal_access_code,generate_access_code
from app.canary_sign_service import _save_case_file
from app.timeutil import utcnow
from tests.ledger_test_helpers import add_user,add_case

@pytest.fixture
def sample(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL fixture required")
    assert os.getenv('CANARY_BACKGROUND_JOBS_ENABLED')=='0'
    with SessionLocal() as db:
        settings=db.get(FirmSettings,1)
        settings.client_portal_enabled=True;settings.mandate_two_factor=False;settings.mandate_password_rotation=False
        cat=UserPermissionCategory(name='audit-'+uuid.uuid4().hex,perm_fee_earner=True)
        db.add(cat);db.commit()
        admin=add_user(db);staff=add_user(db,role=UserRole.user,permission_category_id=cat.id)
        case=add_case(db,fee_earner_user_id=admin.id);case.lock_mode=CaseLockMode.allow_list;case.portal_enabled=True
        contact=Contact(type=ContactType.person,name='Synthetic restricted client',email=uuid.uuid4().hex+'@example.com');db.add(contact);db.flush()
        db.add(CaseContact(case_id=case.id,contact_id=contact.id,type=ContactType.person,name=contact.name))
        access=ContactPortalAccess(contact_id=contact.id,created_by_user_id=admin.id,enabled=True)
        code=generate_access_code();store_portal_access_code(access,code);db.add(access)
        f=_save_case_file(db,case_id=case.id,owner_id=admin.id,folder_path='Shared',filename='synthetic-secret.eml',mime_type='message/rfc822',raw=b'Subject: Synthetic private\r\n\r\nRestricted fixture')
        grant=ContactPortalGrant(contact_id=contact.id,case_id=case.id,folder_path='Shared',label='Synthetic share',created_by_user_id=admin.id,can_download=True,can_upload=False);db.add(grant);db.commit()
        result={k:str(v) for k,v in dict(admin=admin.id,staff=staff.id,case=case.id,contact=contact.id,file=f.id,grant=grant.id).items()}
        result['code']=code;result['headers']={'Authorization':'Bearer '+create_access_token(user_id=str(staff.id),role='user',auth_token_version=staff.auth_token_version)}
        result['admin_headers']={'Authorization':'Bearer '+create_access_token(user_id=str(admin.id),role='admin',auth_token_version=admin.auth_token_version)}
        return result



def allow_staff(s):
    with SessionLocal() as db:
        db.add(CaseAccessRule(case_id=uuid.UUID(s['case']),user_id=uuid.UUID(s['staff']),mode=CaseAccessMode.allow))
        db.commit()


@pytest.mark.parametrize('method,suffix,body', [
    ('get','/access',None), ('get','/grants',None),
    ('post','/access',{}), ('post','/access/rotate',{}),
    ('patch','/access',{'enabled':False}), ('delete','/access',None),
    ('patch','/access/notifications',{'notify_files_added':False}),
    ('post','/access/email',{'access_code':'placeholder'}),
])
def test_restricted_contact_operations_are_denied_without_mutation(sample,method,suffix,body):
    s=sample
    with TestClient(app) as c:
        assert c.get('/cases/'+s['case'],headers=s['headers']).status_code==403
        if suffix=='/access/email': body={'access_code':s['code']}
        response=c.request(method,'/contacts/'+s['contact']+'/portal'+suffix,json=body,headers=s['headers'])
        assert response.status_code==403,response.text
        out=c.get('/contacts/'+s['contact']+'/portal/access',headers=s['admin_headers'])
        assert out.status_code==200 and out.json()['access_code']==s['code']
    with SessionLocal() as db:
        assert db.get(ContactPortalGrant,uuid.UUID(s['grant'])) is not None


@pytest.mark.parametrize('context',['omitted','restricted','accessible'])
def test_rotation_checks_all_contact_matters(sample,context):
    s=sample
    with SessionLocal() as db:
        other=add_case(db,fee_earner_user_id=uuid.UUID(s['staff']))
        db.add(CaseContact(case_id=other.id,contact_id=uuid.UUID(s['contact']),type=ContactType.person,name='Shared contact'))
        db.commit();other_id=str(other.id)
    payload={'send_email':False}
    if context!='omitted':payload['case_id']=s['case'] if context=='restricted' else other_id
    with TestClient(app) as c:
        assert c.post('/contacts/'+s['contact']+'/portal/access/rotate',json=payload,headers=s['headers']).status_code==403


def test_retained_grants_still_protect_credentials(sample):
    s=sample
    with SessionLocal() as db:
        from sqlalchemy import delete
        db.execute(delete(CaseContact).where(CaseContact.contact_id==uuid.UUID(s['contact'])))
        db.commit()
    with TestClient(app) as c:
        assert c.get('/contacts/'+s['contact']+'/portal/access',headers=s['headers']).status_code==403


def test_authorized_staff_can_read_and_rotate(sample):
    s=sample;allow_staff(s)
    with TestClient(app) as c:
        base='/contacts/'+s['contact']+'/portal'
        assert c.get(base+'/access',headers=s['headers']).json()['access_code']==s['code']
        response=c.post(base+'/access/rotate',json={'send_email':False},headers=s['headers'])
        assert response.status_code==200 and response.json()['access_code']!=s['code']
        assert c.get(base+'/grants',headers=s['headers']).status_code==200


@pytest.mark.parametrize('resolution',['join_existing','revoke_other'])
@pytest.mark.parametrize('operation',['/access','/access/rotate'])
def test_email_conflict_cannot_target_restricted_contact(sample,resolution,operation):
    s=sample
    with SessionLocal() as db:
        original=db.get(Contact,uuid.UUID(s['contact']))
        other=Contact(type=ContactType.person,name='Synthetic duplicate',email=original.email)
        db.add(other);db.commit();other_id=str(other.id)
    with TestClient(app) as c:
        response=c.post('/contacts/'+other_id+'/portal'+operation,json={'send_email':False,'conflict_resolution':resolution},headers=s['headers'])
        assert response.status_code==403,response.text
        assert c.get('/contacts/'+s['contact']+'/portal/access',headers=s['admin_headers']).json()['access_code']==s['code']


def test_merge_denies_inaccessible_records_and_admin_merge_still_works(sample):
    s=sample
    with SessionLocal() as db:
        survivor=Contact(type=ContactType.person,name='Synthetic survivor',email=uuid.uuid4().hex+'@example.com')
        db.add(survivor);db.commit();sid=str(survivor.id)
        from app.contact_merge_service import merge_contacts
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as caught:
            merge_contacts(db,survivor_id=survivor.id,source_id=uuid.UUID(s['contact']),actor=db.get(User,uuid.UUID(s['staff'])))
        assert caught.value.status_code==403
    with TestClient(app) as c:
        base='/contacts/'+sid
        assert c.get(base+'/merge-preview',params={'source_contact_id':s['contact']},headers=s['headers']).status_code==403
        assert c.post(base+'/merge',json={'source_contact_id':s['contact'],'send_email':False},headers=s['headers']).status_code==403
        with SessionLocal() as db:
            assert db.get(Contact,uuid.UUID(s['contact'])) is not None
            assert str(db.scalar(select(CaseContact).where(CaseContact.case_id==uuid.UUID(s['case']))).contact_id)==s['contact']
        assert c.get(base+'/merge-preview',params={'source_contact_id':s['contact']},headers=s['admin_headers']).status_code==200
        response=c.post(base+'/merge',json={'source_contact_id':s['contact'],'send_email':False},headers=s['admin_headers'])
        assert response.status_code==200,response.text
    with SessionLocal() as db:
        assert db.get(Contact,uuid.UUID(s['contact'])) is None
        assert str(db.scalar(select(CaseContact).where(CaseContact.case_id==uuid.UUID(s['case']))).contact_id)==sid


@pytest.mark.parametrize('combined',[False,True])
def test_staff_cannot_promote_themselves_to_access_manager(sample,combined):
    s=sample;allow_staff(s)
    with TestClient(app) as c:
        path='/cases/'+s['case'];payload={'fee_earner_user_id':s['staff']}
        if combined:payload['lock_mode']='none'
        assert c.patch(path,json=payload,headers=s['headers']).status_code==403
        assert c.patch(path,json={'lock_mode':'none'},headers=s['headers']).status_code==403
        # Normal edits carrying the unchanged assignment remain allowed.
        assert c.patch(path,json={'fee_earner_user_id':s['admin'],'matter_description':'Ordinary edit'},headers=s['headers']).status_code==200
        assert c.patch(path,json={'fee_earner_user_id':s['staff']},headers=s['admin_headers']).status_code==200
        assert c.patch(path,json={'lock_mode':'none'},headers=s['headers']).status_code==200
        # The newly assigned non-admin fee earner may hand responsibility back.
        assert c.patch(path,json={'fee_earner_user_id':s['admin']},headers=s['headers']).status_code==200


@pytest.mark.parametrize('state',['denied','allowed','wrong_file','expired'])
def test_pending_preview_validates_access_and_file_without_claiming(sample,state):
    s=sample
    if state!='denied':allow_staff(s)
    with SessionLocal() as db:
        if state=='wrong_file':
            other=add_case(db,fee_earner_user_id=uuid.UUID(s['admin']))
            db.get(File,uuid.UUID(s['file'])).case_id=other.id
        u=db.get(User,uuid.UUID(s['staff']))
        u.outlook_pending_eml_open_case_id=uuid.UUID(s['case']);u.outlook_pending_eml_open_file_id=uuid.UUID(s['file'])
        u.outlook_pending_eml_open_expires_at=utcnow()+timedelta(minutes=-5 if state=='expired' else 5);db.commit()
    with TestClient(app) as c:
        response=c.get('/outlook-plugin/pending-eml-open',headers=s['headers'])
        assert response.status_code==200
        body=response.json()
        assert body['active']==(state=='allowed')
        if state!='allowed':
            assert not body.get('filename') and not body.get('case_id') and not body.get('file_id')
        else:
            assert body['filename']=='synthetic-secret.eml'
        with SessionLocal() as db:
            u=db.get(User,uuid.UUID(s['staff']))
            assert (u.outlook_pending_eml_open_file_id is not None)==(state=='allowed')
        claim=c.post('/outlook-plugin/pending-eml-open/claim',headers=s['headers'])
        assert claim.status_code==200 and claim.json()['active']==(state=='allowed')


def test_matter_portal_link_without_contact_card_link_is_checked(sample):
    s = sample
    from sqlalchemy import delete
    from app.models import MatterPortalAccess
    from app.portal_service import store_matter_portal_access_code
    with SessionLocal() as db:
        db.execute(delete(CaseContact).where(CaseContact.contact_id == uuid.UUID(s['contact'])))
        db.execute(delete(ContactPortalGrant).where(ContactPortalGrant.contact_id == uuid.UUID(s['contact'])))
        row = MatterPortalAccess(case_id=uuid.UUID(s['case']), contact_id=uuid.UUID(s['contact']), created_by_user_id=uuid.UUID(s['admin']), enabled=False)
        store_matter_portal_access_code(row, generate_access_code())
        db.add(row)
        db.commit()
    with TestClient(app) as c:
        assert c.get('/contacts/' + s['contact'] + '/portal/access', headers=s['headers']).status_code == 403


def test_authorized_staff_can_manage_contact_login_lifecycle(sample):
    s = sample
    allow_staff(s)
    with TestClient(app) as c:
        base = '/contacts/' + s['contact'] + '/portal'
        assert c.patch(base + '/access/notifications', json={'notify_files_added': False}, headers=s['headers']).status_code == 200
        assert c.patch(base + '/access', json={'enabled': False}, headers=s['headers']).status_code == 200
        assert c.post(base + '/access', json={'send_email': False}, headers=s['headers']).status_code == 201
        assert c.delete(base + '/access', headers=s['headers']).status_code == 204
        assert c.get(base + '/access', headers=s['headers']).json()['access_record_exists'] is False
        assert c.get(base + '/grants', headers=s['headers']).json() == []


def test_permission_category_admin_can_merge(sample):
    s = sample
    with SessionLocal() as db:
        staff = db.get(User, uuid.UUID(s['staff']))
        db.get(UserPermissionCategory, staff.permission_category_id).perm_admin = True
        survivor = Contact(type=ContactType.person, name='Admin category survivor', email=uuid.uuid4().hex + '@example.com')
        db.add(survivor)
        db.commit()
        sid = str(survivor.id)
    with TestClient(app) as c:
        response = c.post('/contacts/' + sid + '/merge', json={'source_contact_id': s['contact'], 'send_email': False}, headers=s['headers'])
        assert response.status_code == 200, response.text


@pytest.mark.parametrize('kind', ['quote', 'form', 'canary_sign', 'docusign'])
def test_retained_portal_resources_protect_global_login(sample, kind):
    s = sample
    from sqlalchemy import delete
    from app.models import (
        QuotePortalDelivery, PortalFormTemplate, PortalFormSubmission,
        CanarySignRequest, CanarySignRecipient, DocusignSigningRequest, DocusignSigningRecipient,
    )
    cid, contact, fid = (uuid.UUID(s[k]) for k in ('case', 'contact', 'file'))
    with SessionLocal() as db:
        db.execute(delete(CaseContact).where(CaseContact.contact_id == contact))
        db.execute(delete(ContactPortalGrant).where(ContactPortalGrant.contact_id == contact))
        if kind == 'quote':
            db.add(QuotePortalDelivery(case_id=cid, contact_id=contact, file_id=fid, file_version_at_send=1))
        elif kind == 'form':
            template = PortalFormTemplate(name='Synthetic retained form', reference=uuid.uuid4().hex, owner_id=uuid.UUID(s['admin']))
            db.add(template)
            db.flush()
            db.add(PortalFormSubmission(case_id=cid, contact_id=contact, template_id=template.id))
        else:
            request_model, recipient_model = (
                (CanarySignRequest, CanarySignRecipient) if kind == 'canary_sign'
                else (DocusignSigningRequest, DocusignSigningRecipient)
            )
            kwargs = {'expires_at': utcnow() + timedelta(days=1)} if kind == 'canary_sign' else {}
            request = request_model(case_id=cid, source_file_id=fid, **kwargs)
            db.add(request)
            db.flush()
            kwargs = {'client_user_id': uuid.uuid4().hex} if kind == 'docusign' else {}
            db.add(recipient_model(signing_request_id=request.id, contact_id=contact, name='Synthetic recipient', email='synthetic@example.com', sign_token=uuid.uuid4().hex, **kwargs))
        db.commit()
    with TestClient(app) as c:
        path = '/contacts/' + s['contact'] + '/portal/access'
        assert c.get(path, headers=s['headers']).status_code == 403
        assert c.get(path, headers=s['admin_headers']).status_code == 200
