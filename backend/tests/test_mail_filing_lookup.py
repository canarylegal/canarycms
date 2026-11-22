import uuid
import sys
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import File, CaseLockMode
from app.canary_sign_service import _save_case_file
from app.timeutil import utcnow
from tests.ledger_test_helpers import add_case
from tests.test_permission_boundaries_postgres import sample, allow_staff

MID='<synthetic-mail@example.com>'
@pytest.fixture(autouse=True)
def unique_message_identity(monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "MID", "<"+uuid.uuid4().hex+"@example.com>")

def eml(mid=None):
    mid = mid or MID
    return ('From: sender@example.com\r\nTo: recipient@example.com\r\nSubject: Synthetic mail\r\nMessage-ID: '+mid+'\r\n\r\nSynthetic body').encode()

def save(s,case_id,raw=None,name='fixture.eml',mid=None,folder='Mail',newer=False):
    mid = mid or MID
    with SessionLocal() as db:
        f=_save_case_file(db,case_id=uuid.UUID(case_id),owner_id=uuid.UUID(s['admin']),folder_path=folder,filename=name,mime_type='message/rfc822' if name.endswith('.eml') else 'application/pdf',raw=raw if raw is not None else eml())
        f.source_internet_message_id=mid;f.source_outlook_item_id='same-provider-id';f.source_outlook_conversation_id='same-thread';f.source_imap_mbox='INBOX';f.source_imap_uid='7'
        if newer:f.created_at=utcnow()+timedelta(days=1)
        db.commit();return str(f.id)

@pytest.mark.parametrize('name,raw,expected',[('mail.eml',eml(),MID),('letter.pdf',b'%PDF synthetic',None),('duplicate.eml',eml(MID+'\r\nMessage-ID: <other@example.com>'),None),('missing.eml',b'From: a@example.com\r\n\r\nNo id',None)])
def test_upload_identity_comes_from_parent_email_content(sample,name,raw,expected):
    with TestClient(app) as c:
        r=c.post('/cases/'+sample['case']+'/files',headers=sample['admin_headers'],files={'upload':(name,raw,'application/octet-stream')},data={'source_internet_message_id':'<forged@example.com>','outlook_item_id':'forged-provider','outlook_conversation_id':'forged-thread','source_imap_mbox':'INBOX','source_imap_uid':'8'})
        assert r.status_code==201,r.text
    with SessionLocal() as db:
        f=db.get(File,uuid.UUID(r.json()['id']));assert f.source_internet_message_id==expected
        if name.endswith('.pdf'):
            assert not any([f.source_outlook_item_id,f.source_outlook_conversation_id,f.source_imap_mbox,f.source_imap_uid,f.outlook_graph_message_id])


def test_attachment_cannot_supply_parent_identity(sample):
    parent=save(sample,sample['case'])
    with TestClient(app) as c:
        r=c.post('/cases/'+sample['case']+'/files',headers=sample['admin_headers'],files={'upload':('attached.eml',eml(),'message/rfc822')},data={'parent_file_id':parent,'source_internet_message_id':MID,'outlook_item_id':'forged','source_imap_uid':'8','source_imap_mbox':'INBOX'})
        assert r.status_code==201,r.text
    with SessionLocal() as db:
        f=db.get(File,uuid.UUID(r.json()['id']));assert f.source_internet_message_id is None and f.source_outlook_item_id is None and f.source_imap_uid is None

@pytest.mark.parametrize('route',['/outlook-plugin/linked-case','/mail-plugin/linked-case','/mail-plugin/message-context'])
def test_multiple_locations_are_candidates_never_automatic_context(sample,route):
    s=sample;allow_staff(s)
    with SessionLocal() as db:
        other=add_case(db,fee_earner_user_id=uuid.UUID(s['staff']));other.lock_mode=CaseLockMode.none;db.commit();otherid=str(other.id)
    ids={save(s,s['case']),save(s,otherid,newer=True)}
    with TestClient(app) as c:
        r=c.post(route,headers=s['headers'],json={'internet_message_id':MID,'conversation_id':'same-thread'});assert r.status_code==200,r.text
    body=r.json();assert {m['file_id'] for m in body['matches']}==ids
    assert body['requires_confirmation'] is True and body['lookup_status']=='possible_matches'
    assert body.get('linked_case') is None and not body.get('found') and body.get('case_id') is None


def test_forged_legacy_metadata_and_thread_matches_cannot_override_exact_email(sample):
    s=sample;allow_staff(s);good=save(s,s['case'])
    save(s,s['case'],raw=b'%PDF fake',name='fake.pdf',newer=True)
    save(s,s['case'],raw=eml('<different@example.com>'),newer=True)
    save(s,s['case'],raw=eml('<different@example.com>'),mid='<different@example.com>',newer=True)
    with TestClient(app) as c:
        body=c.post('/outlook-plugin/linked-case',headers=s['headers'],json={'internet_message_id':MID,'conversation_id':'same-thread','outlook_item_id':'same-provider-id'}).json()
    assert [m['file_id'] for m in body['matches']]==[good]

@pytest.mark.parametrize('payload',[{'conversation_id':'same-thread'},{'outlook_item_id':'same-provider-id'},{'source_imap_mbox':'INBOX','source_imap_uid':'7'},{'internet_message_id':'bad-id'},{}])
def test_unscoped_identifiers_never_establish_filing(sample,payload):
    s=sample;allow_staff(s);save(s,s['case'])
    with TestClient(app) as c:r=c.post('/mail-plugin/linked-case',headers=s['headers'],json=payload)
    assert r.status_code==200 and r.json()['matches']==[] and r.json()['lookup_status']=='no_exact_identifier'


def test_access_filter_before_paging_and_no_forty_row_starvation(sample):
    s=sample
    with SessionLocal() as db:
        other=add_case(db,fee_earner_user_id=uuid.UUID(s['staff']));other.lock_mode=CaseLockMode.none;db.commit();otherid=str(other.id)
    expected={save(s,otherid) for _ in range(52)}
    for _ in range(45):save(s,s['case'],newer=True)
    with TestClient(app) as c:
        first=c.post('/mail-plugin/linked-case',headers=s['headers'],json={'internet_message_id':MID}).json()
        second=c.post('/mail-plugin/linked-case',headers=s['headers'],json={'internet_message_id':MID,'offset':first['next_offset']}).json()
    assert len(first['matches'])==50 and len(second['matches'])==2
    assert {m['file_id'] for m in first['matches']+second['matches']}==expected
    assert second['next_offset'] is None
    assert all(m['id']==otherid for m in first['matches']+second['matches'])


def test_restricted_only_is_indistinguishable_from_no_match(sample):
    save(sample,sample['case'])
    with TestClient(app) as c:
        hidden=c.post('/mail-plugin/message-context',headers=sample['headers'],json={'internet_message_id':MID}).json()
        absent=c.post('/mail-plugin/message-context',headers=sample['headers'],json={'internet_message_id':'<absent@example.com>'}).json()
    assert hidden==absent


def test_fabricated_eml_is_only_an_unconfirmed_candidate(sample):
    s=sample;allow_staff(s)
    fake=save(s,s['case'],raw=eml().replace(b'Synthetic body',b'Fabricated body claiming another message identity'))
    with TestClient(app) as c:
        body=c.post('/mail-plugin/message-context',headers=s['headers'],json={'internet_message_id':MID}).json()
    assert [m['file_id'] for m in body['matches']]==[fake]
    assert body['requires_confirmation'] and not body['found'] and body['case_id'] is None
