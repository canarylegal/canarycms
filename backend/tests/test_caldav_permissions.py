import hashlib
import hmac
import json
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User, UserCalendar, UserCalendarShare, UserCalendarSubscription
from app.caldav_permissions import calendar_rights
from tests.test_permission_boundaries_postgres import sample

@pytest.fixture
def calendars(sample):
    with SessionLocal() as db:
        for key in ('admin','staff'):
            db.get(User,uuid.UUID(sample[key])).caldav_password_enc='synthetic-enabled'
        personal=UserCalendar(owner_user_id=uuid.UUID(sample['admin']),name='Private',radicale_slug='canary')
        shared=UserCalendar(owner_user_id=uuid.UUID(sample['admin']),name='Team',radicale_slug='team',is_public=False)
        db.add_all([personal,shared]);db.commit()
        return sample,shared.id

@pytest.mark.parametrize('method',['GET','HEAD','PROPFIND','REPORT','PUT','DELETE','MKCALENDAR','PROPPATCH','MOVE'])
def test_unshared_calendars_are_private(calendars,method):
    s,cid=calendars
    with SessionLocal() as db:
        assert calendar_rights(db,s['staff'],f"/{s['admin']}/canary/",method,f"/{s['admin']}/canary/event.ics")==''
        assert calendar_rights(db,s['staff'],f"/{s['admin']}/",method,f"/{s['admin']}/")==''
        assert calendar_rights(db,s['admin'],f"/{s['admin']}/canary/",method,f"/{s['admin']}/canary/event.ics")=='rw'

@pytest.mark.parametrize('write',[False,True])
def test_share_levels_and_revocation(calendars,write):
    s,cid=calendars
    with SessionLocal() as db:
        share=UserCalendarShare(calendar_id=cid,grantee_user_id=uuid.UUID(s['staff']),can_write=write)
        db.add(share);db.commit()
        path=f"/{s['admin']}/team/"
        assert calendar_rights(db,s['staff'],path,'REPORT',path)==('rw' if write else 'r')
        assert calendar_rights(db,s['staff'],path,'PUT',path+'item.ics')==('rw' if write else 'r')
        for method in ['DELETE','PROPPATCH','MKCALENDAR','PUT','MOVE']:
            assert calendar_rights(db,s['staff'],path,method,path)=='r'
        db.delete(share);db.commit()
        assert calendar_rights(db,s['staff'],path,'GET',path)==''


def test_public_requires_subscription_and_honors_unpublish(calendars):
    s,cid=calendars;path=f"/{s['admin']}/team/"
    with SessionLocal() as db:
        cal=db.get(UserCalendar,cid);cal.is_public=True;db.commit()
        assert calendar_rights(db,s['staff'],path,'GET',path)==''
        db.add(UserCalendarSubscription(calendar_id=cid,subscriber_user_id=uuid.UUID(s['staff'])));db.commit()
        assert calendar_rights(db,s['staff'],path,'GET',path)=='r'
        cal.is_public=False;db.commit()
        assert calendar_rights(db,s['staff'],path,'GET',path)==''

@pytest.mark.parametrize('field,value',[('is_active',False),('caldav_password_enc',None)])
def test_disabled_accounts_or_caldav_denied(calendars,field,value):
    s,_=calendars
    with SessionLocal() as db:
        setattr(db.get(User,uuid.UUID(s['admin'])),field,value);db.commit()
        assert calendar_rights(db,s['admin'],f"/{s['admin']}/canary/",'GET','/')==''


def test_callback_requires_service_proof_and_fresh_timestamp(calendars,monkeypatch,tmp_path):
    from app.routers import caldav_rights
    s,_=calendars;file=tmp_path/'users';file.write_bytes(b'synthetic-private-credential-file')
    monkeypatch.setattr(caldav_rights,'htpasswd_path',lambda:file)
    payload={'user':s['admin'],'path':f"/{s['admin']}/canary/",'method':'GET','request_path':'/','timestamp':time.time()}
    def signed(p):
        body=json.dumps(p).encode();key=hashlib.sha256(b'canary-caldav-rights-v1\0'+file.read_bytes()).digest()
        return body,{'X-Canary-DAV-Signature':hmac.new(key,body,hashlib.sha256).hexdigest()}
    with TestClient(app) as c:
        assert c.post('/internal/caldav/rights',json=payload,headers=s['admin_headers']).status_code==403
        body,headers=signed(payload)
        r=c.post('/internal/caldav/rights',content=body,headers=headers);assert r.status_code==200 and r.json()=={'rights':'rw'}
        assert c.post('/internal/caldav/rights',content=body+b' ',headers=headers).status_code==403
        payload['timestamp']-=60;body,headers=signed(payload)
        assert c.post('/internal/caldav/rights',content=body,headers=headers).status_code==403
        assert c.post('/internal/caldav/rights',content=b'x'*4097).status_code==413
