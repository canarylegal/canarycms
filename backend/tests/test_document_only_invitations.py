"""Real document services and scoped HTTP sessions; synthetic PDFs and captured mail only."""
import json
import uuid
import pytest
from sqlalchemy import select,delete
from fastapi import HTTPException
from app.db import SessionLocal
from app.models import ContactPortalAccess, Contact, CaseContact, User, CanarySignRecipient, CanarySignRequest, PortalFormSubmission, QuotePortalDelivery, NotificationOutbox
from app import canary_sign_service as sign, portal_form_service as forms, quote_portal_service as quotes
from app.portal_invitation import issue
from app.document_invitation_access import binding
from app.email_crypt import decrypt_password
from tests.test_portal_access_postgres import safe,data,url

@pytest.fixture
def messages(monkeypatch):
    monkeypatch.setattr(quotes, "_notify_staff_quote_response", lambda *a, **k: None)
    captured=[]
    def send(db,kind,**kwargs):captured.append((kind,kwargs));return True
    monkeypatch.setattr(forms,'dispatch_alert',send)
    monkeypatch.setattr(quotes,'dispatch_alert',send)
    return captured


def access_state(db,contact):
    row=db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id==contact))
    return None if row is None else (row.id,row.enabled,row.code_sha256,row.session_version,row.failed_attempts,row.locked_until,row.expires_at)


@pytest.mark.parametrize('kind',['form','quote','sign'])
@pytest.mark.parametrize('state',['absent','disabled','active'])
def test_send_and_resend_never_provision_login_and_invitation_is_document_only(data,messages,kind,state):
    d=data
    with SessionLocal() as db:
        access=db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id==d['contact']))
        if state=='absent':db.delete(access)
        elif state=='disabled':access.enabled=False
        db.commit();before=access_state(db,d['contact'])
        if kind=='form':
            old=db.get(PortalFormSubmission,d['sub'])
            from app.models import PortalFormSubmissionStatus
            old.status=PortalFormSubmissionStatus.voided;db.flush()
            row,*_=forms.send_form_to_contact(db,case_id=d['cid'],template_id=old.template_id,contact_id=d['contact'],actor=db.get(User,d['uid']))
            first=issue(db,kind,row)
            forms.resend_form_submission(db,submission=row,actor=db.get(User,d['uid']))
            second=issue(db,kind,row)
        elif kind=='quote':
            row,*_=quotes.send_quote_via_portal(db,case_id=d['cid'],file_id=db.get(CanarySignRequest,d['rid']).source_file_id,contact_id=d['contact'],actor_user_id=d['uid'])
            first=issue(db,kind,row)
            quotes.resend_quote_delivery(db,delivery=row,actor_user_id=d['uid'])
            second=issue(db,kind,row)
        else:
            previous=db.get(CanarySignRequest,d['rid'])
            from app.models import CanarySignStatus
            previous.status=CanarySignStatus.voided;db.flush()
            contact=db.get(Contact,d['contact'])
            row=sign.send_signing_request(db,case_id=d['cid'],source_file_id=previous.source_file_id,actor=db.get(User,d['uid']),subject='Synthetic invitation',recipient_specs=[{'contact_id':contact.id,'email':contact.email,'name':contact.name}],fields_specs=[{'field_type':'signature','page':1,'x_pct':10,'y_pct':10,'w_pct':30,'h_pct':10}])
            recipient=db.scalar(select(CanarySignRecipient).where(CanarySignRecipient.signing_request_id==row.id))
            first=recipient.sign_token
            sign.remind_signing_request(db,req=row,actor=db.get(User,d['uid']))
            db.refresh(recipient);second=recipient.sign_token
            mails=db.scalars(select(NotificationOutbox).where(NotificationOutbox.signing_request_id==row.id)).all()
            assert mails
            for mail in mails:
                payload=decrypt_password(mail.payload_enc)
                assert 'Your access code' not in payload and 'access_code' not in payload
        db.commit();assert access_state(db,d['contact'])==before
        identity=row.id
    if kind!='sign':
        assert messages and all('access_code' not in m[1]['context'] for m in messages)
        assert all(m[1]['to_email']=='signer0@example.com' for m in messages)
    endpoint='/portal/canary-sign-exchange' if kind=='sign' else '/portal/'+kind+'-exchange'
    key='sign_token' if kind=='sign' else 'exchange_token'
    assert first!=second
    assert d['client'].post(endpoint,json={key:first}).status_code==401
    response=d['client'].post(endpoint,json={key:second});assert response.status_code==200,response.text
    h={'Authorization':'Bearer '+response.json()['session_token']}
    session=d['client'].get('/portal/session',headers=h);assert session.status_code==200,session.text
    assert session.json()['grants']==[]
    assert d['client'].get(url(d,'file'),headers=h).status_code==403
    path=f'/portal/'+('canary-sign' if kind=='sign' else 'forms' if kind=='form' else 'quote-deliveries')+f'/{identity}'
    own=d['client'].get(path,headers=h);assert own.status_code==200,own.text
    if kind == 'form':
        done=d['client'].post(path+'/submit',headers=h,json={'responses':{}})
    elif kind == 'quote':
        assert d['client'].get(path+'/file',headers=h).status_code==200
        done=d['client'].post(path+'/respond',headers=h,json={'accepted':True})
    else:
        assert d['client'].get(path+'/pdf',headers=h).status_code==200
        values={field['id']:{'text':'Synthetic signature'} for field in own.json()['fields']}
        done=d['client'].post(path+'/sign',headers=h,json={'field_values':values,'consent':True})
    assert done.status_code==200,done.text
    assert d['client'].post(endpoint,json={key:second}).status_code==401
    assert d['client'].get(path,headers=h).status_code==200
    with SessionLocal() as db:assert access_state(db,d['contact'])==before


@pytest.mark.parametrize('change',['foreign_contact','foreign_case_contact','mismatched_ids','email_override','no_contact'])
def test_sign_recipient_rejected_before_artifacts_or_mail(data,change):
    d=data
    with SessionLocal() as db:
        contact=db.get(Contact,d['contact']);req=db.get(CanarySignRequest,d['rid'])
        cc=db.scalar(select(CaseContact).where(CaseContact.case_id==d['cid'],CaseContact.contact_id==contact.id))
        spec={'contact_id':contact.id,'case_contact_id':cc.id,'email':contact.email,'name':contact.name}
        if change=='foreign_contact':spec={'contact_id':d['other'],'email':'chosen@example.test','name':'Chosen'}
        elif change=='foreign_case_contact':spec['case_contact_id']=uuid.uuid4()
        elif change=='mismatched_ids':spec['contact_id']=d['other']
        elif change=='email_override':spec['email']='chosen@example.test'
        else:spec={'email':'chosen@example.test','name':'Chosen'}
        before=list(db.scalars(select(CanarySignRequest.id).where(CanarySignRequest.case_id==d['cid'])))
        with pytest.raises(HTTPException) as error:
            sign.send_signing_request(db,case_id=d['cid'],source_file_id=req.source_file_id,actor=db.get(User,d['uid']),subject='Denied',recipient_specs=[spec])
        assert error.value.status_code==400
        assert list(db.scalars(select(CanarySignRequest.id).where(CanarySignRequest.case_id==d['cid'])))==before


@pytest.mark.parametrize('kind',['form','quote','sign'])
@pytest.mark.parametrize('change',['email','removed'])
def test_document_sessions_revoke_on_matter_contact_changes(data,kind,change):
    d=data
    with SessionLocal() as db:
        if kind=='form':row=db.get(PortalFormSubmission,d['sub']);token=issue(db,kind,row)
        elif kind=='quote':
            row=QuotePortalDelivery(id=uuid.uuid4(),case_id=d['cid'],contact_id=d['contact'],file_id=d['file'],file_version_at_send=1,sent_by_user_id=d['uid']);db.add(row);db.flush();token=issue(db,kind,row)
        else:
            row=db.get(CanarySignRecipient,d['recip']);token=row.sign_token
        db.commit()
    endpoint='/portal/canary-sign-exchange' if kind=='sign' else '/portal/'+kind+'-exchange'
    key='sign_token' if kind=='sign' else 'exchange_token'
    response=d['client'].post(endpoint,json={key:token});assert response.status_code==200,response.text
    with SessionLocal() as db:
        cc=db.scalar(select(CaseContact).where(CaseContact.case_id==d['cid'],CaseContact.contact_id==d['contact']))
        if change=='email':cc.email='changed@example.test'
        else:db.delete(cc)
        db.commit()
    assert d['client'].post(endpoint,json={key:token}).status_code==401
    assert d['client'].get('/portal/session',headers={'Authorization':'Bearer '+response.json()['session_token']}).status_code in (401,403)


def test_document_only_sign_mail_dispatches_without_portal_account_and_rechecks_email(data,monkeypatch):
    from app import canary_sign_delivery as delivery
    from app.alert_dispatch import AlertKind
    monkeypatch.setattr(delivery,'resolve_alert_transport',lambda db:'smtp')
    d=data
    def queue():
        with SessionLocal() as db:
            req=db.get(CanarySignRequest,d['rid']);r=db.get(CanarySignRecipient,d['recip'])
            key=str(uuid.uuid4())
            sign._notify_recipients(db,req,[r],kind=AlertKind.canary_sign_requested,event_key=key)
            db.commit()
            return db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.signing_request_id==req.id,NotificationOutbox.event_key==key))
    with SessionLocal() as db:
        db.execute(delete(ContactPortalAccess).where(ContactPortalAccess.contact_id==d['contact']));db.commit()
    first=queue();calls=[]
    def fake(db,message):calls.append(message);return 'smtp'
    assert delivery.deliver(first,actor_id=d['uid'],sender=fake)['state']=='sent'
    assert len(calls)==1
    second=queue()
    with SessionLocal() as db:
        cc=db.scalar(select(CaseContact).where(CaseContact.case_id==d['cid'],CaseContact.contact_id==d['contact']))
        cc.email='changed@example.test';db.commit()
    assert delivery.deliver(second,actor_id=d['uid'],sender=fake)['state']!='sent'
    assert len(calls)==1
    with SessionLocal() as db:assert access_state(db,d['contact']) is None


@pytest.mark.parametrize('kind',['form','quote'])
def test_resend_rejects_contact_removed_from_matter(data,messages,kind):
    d=data
    with SessionLocal() as db:
        if kind=='form':row=db.get(PortalFormSubmission,d['sub'])
        else:
            row=QuotePortalDelivery(id=uuid.uuid4(),case_id=d['cid'],contact_id=d['contact'],file_id=d['file'],file_version_at_send=1,sent_by_user_id=d['uid']);db.add(row);db.flush()
        db.execute(delete(CaseContact).where(CaseContact.case_id==d['cid'],CaseContact.contact_id==d['contact']));db.commit()
        with pytest.raises(HTTPException) as error:
            if kind=='form':forms.resend_form_submission(db,submission=row,actor=db.get(User,d['uid']))
            else:quotes.resend_quote_delivery(db,delivery=row,actor_user_id=d['uid'])
        assert error.value.status_code==400 and messages==[]


def test_final_delivery_holds_recipient_authority_until_provider_returns(data,monkeypatch):
    from app import canary_sign_delivery as delivery
    from app.alert_dispatch import AlertKind
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    monkeypatch.setattr(delivery,'resolve_alert_transport',lambda db:'smtp')
    d=data
    with SessionLocal() as db:
        req=db.get(CanarySignRequest,d['rid']);r=db.get(CanarySignRecipient,d['recip'])
        sign._notify_recipients(db,req,[r],kind=AlertKind.canary_sign_requested,event_key=str(uuid.uuid4()))
        db.commit()
        identity=db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.signing_request_id==req.id))
        ccid=r.case_contact_id
    entered=Event();release=Event();changing=Event()
    def sender(db,message):entered.set();assert release.wait(10);return 'smtp'
    def change():
        with SessionLocal() as db:
            row=db.get(CaseContact,ccid);row.email='changed@example.test';changing.set();db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        send=pool.submit(delivery.deliver,identity,actor_id=d['uid'],sender=sender)
        try:
            assert entered.wait(10)
            edit=pool.submit(change);assert changing.wait(10)
            with pytest.raises(TimeoutError):edit.result(timeout=.15)
        finally:release.set()
        assert send.result(10)['state']=='sent';edit.result(10)


@pytest.mark.parametrize('kind',['form','quote','sign'])
@pytest.mark.parametrize('changed',['matter','firm'])
def test_invitation_mutation_rechecks_cached_feature_authority(data,kind,changed):
    from app.models import Case,FirmSettings
    from app.security import PortalSessionPayload
    from app.portal_policy import authorize
    d=data
    with SessionLocal() as db:
        if kind=='form':row=db.get(PortalFormSubmission,d['sub'])
        elif kind=='sign':row=db.get(CanarySignRecipient,d['recip'])
        else:
            row=QuotePortalDelivery(id=uuid.uuid4(),case_id=d['cid'],contact_id=d['contact'],file_id=d['file'],file_version_at_send=1,sent_by_user_id=d['uid']);db.add(row);db.flush()
        token=issue(db,kind,row);identity=row.id;db.commit()
        cached_case=db.get(Case,d['cid']);cached_firm=db.get(FirmSettings,1)
        assert cached_case.portal_enabled and cached_firm.client_portal_enabled
        with SessionLocal() as revoke:
            if changed=='matter':revoke.get(Case,d['cid']).portal_enabled=False
            else:revoke.get(FirmSettings,1).client_portal_enabled=False
            revoke.commit()
        db.info['portal_session']=PortalSessionPayload(contact_id=str(d['contact']),case_id=str(d['cid']),
            invitation=token,resource_kind=kind,resource_id=str(identity),signing_request_id=str(d['rid']) if kind=='sign' else None)
        with pytest.raises(HTTPException) as error:
            authorize(db,d['cid'],resource_kind=kind,resource_id=identity,signing_request_id=d['rid'] if kind=='sign' else None,lock=True)
        assert error.value.status_code in (401,403)
