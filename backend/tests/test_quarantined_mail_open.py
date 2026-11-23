import uuid
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import File,User
from app.timeutil import utcnow
from tests.test_permission_boundaries_postgres import sample

@pytest.mark.parametrize('state',['pending','blocked','error'])
@pytest.mark.parametrize('prefix',['mail-plugin','outlook-plugin'])
def test_unavailable_email_cannot_be_queued_or_issued_an_open_token(sample,state,prefix):
    with SessionLocal() as db:db.get(File,uuid.UUID(sample['file'])).scan_state=state;db.commit()
    with TestClient(app) as c:
        result=c.put('/'+prefix+'/pending-eml-open',headers=sample['admin_headers'],json={'case_id':sample['case'],'file_id':sample['file']});assert result.status_code==423,result.text
        result=c.post('/cases/'+sample['case']+'/files/'+sample['file']+'/eml-open-token',headers=sample['admin_headers']);assert result.status_code==423,result.text
    with SessionLocal() as db:assert db.get(User,uuid.UUID(sample['admin'])).outlook_pending_eml_open_file_id is None

@pytest.mark.parametrize('state',['pending','blocked','error'])
@pytest.mark.parametrize('claim',[False,True])
def test_preexisting_unavailable_open_request_is_cleared_without_token(sample,state,claim):
    with SessionLocal() as db:
        db.get(File,uuid.UUID(sample['file'])).scan_state=state
        user=db.get(User,uuid.UUID(sample['admin']));user.outlook_pending_eml_open_case_id=uuid.UUID(sample['case']);user.outlook_pending_eml_open_file_id=uuid.UUID(sample['file']);user.outlook_pending_eml_open_expires_at=utcnow()+timedelta(minutes=2);db.commit()
    with TestClient(app) as c:
        response=c.request('POST' if claim else 'GET','/mail-plugin/pending-eml-open'+('/claim' if claim else ''),headers=sample['admin_headers']);assert response.status_code==200,response.text;assert response.json()['active'] is False;assert not response.json().get('open_token')
    with SessionLocal() as db:assert db.get(User,uuid.UUID(sample['admin'])).outlook_pending_eml_open_file_id is None

@pytest.mark.parametrize('state',['unscanned','clean'])
def test_available_email_can_still_be_opened(sample,state):
    with SessionLocal() as db:db.get(File,uuid.UUID(sample['file'])).scan_state=state;db.commit()
    with TestClient(app) as c:
        result=c.put('/mail-plugin/pending-eml-open',headers=sample['admin_headers'],json={'case_id':sample['case'],'file_id':sample['file']});assert result.status_code==200,result.text
        result=c.post('/mail-plugin/pending-eml-open/claim',headers=sample['admin_headers']);assert result.status_code==200 and result.json()['open_token']
