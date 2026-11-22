import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import User,FirmSettings,WebAuthnChallenge
from app.routers.webauthn import _store_challenge
from app.mail_plugin_auth_service import create_plugin_auth_code
from tests.test_permission_boundaries_postgres import sample

@pytest.mark.parametrize('mandate',[False,True])
def test_admin_factor_reset_revokes_sessions_approvals_and_challenges(sample,monkeypatch,mandate):
    s=sample;monkeypatch.setenv('CANARY_PUBLIC_URL','https://canary.example.com')
    state=uuid.uuid4().hex
    with SessionLocal() as db:
        user=db.get(User,uuid.UUID(s['staff']));user.is_2fa_enabled=True
        before=user.auth_token_version
        code=create_plugin_auth_code(db,user=user,client='thunderbird',state=state,redirect_uri='https://canary.example.com/connect/mail-plugin/callback')
        _store_challenge(db,kind='register_begin',subject=s['staff'],challenge=b'synthetic')
    with TestClient(app) as client:
        assert client.post('/admin/users/'+s['staff']+'/disable-2fa',headers=s['admin_headers']).status_code==204
        with SessionLocal() as db:
            assert db.get(User,uuid.UUID(s['staff'])).auth_token_version==before+1
            assert db.scalar(select(WebAuthnChallenge).where(WebAuthnChallenge.subject==s['staff'])) is None
            db.get(FirmSettings,1).mandate_two_factor=mandate;db.commit()
        for path in ['/contacts','/auth/me']:
            assert client.get(path,headers=s['headers']).status_code==401
        for path,body in [('/auth/webauthn/register/begin',None),('/auth/webauthn/register/finish',{'credential':{}}),('/auth/2fa/setup',{})]:
            result=client.post(path,json=body,headers=s['headers']);assert result.status_code==401,result.text
        result=client.post('/auth/plugin/token',json={'client':'thunderbird','state':state,'code':code})
        assert result.status_code==401,result.text

@pytest.mark.parametrize('error',[RuntimeError,ValueError])
def test_support_failure_hides_exception_and_logs_details(sample,monkeypatch,caplog,error):
    from app.routers import support
    marker='SYNTHETIC-INTERNAL-TRANSPORT-DETAIL'
    def fail(*args,**kwargs):raise error(marker)
    monkeypatch.setattr(support,'send_firm_email',fail)
    with TestClient(app) as client:
        response=client.post('/support/ticket',json={'kind':'bug','subject':'Synthetic','message':'Synthetic failure','urgency':1},headers=sample['headers'])
    assert response.status_code==503
    assert marker not in response.text
    assert response.json()['detail']=='Could not send the ticket e-mail. Please try again later.'
    assert marker in caplog.text


def test_reset_allows_fresh_password_login_and_new_enrollment(sample):
    from app.security import hash_password
    s=sample;password='Synthetic-recovery-password-94!'
    with SessionLocal() as db:
        user=db.get(User,uuid.UUID(s['staff']));user.password_hash=hash_password(password);email=user.email;db.commit()
    with TestClient(app) as client:
        assert client.post('/admin/users/'+s['staff']+'/disable-2fa',headers=s['admin_headers']).status_code==204
        with SessionLocal() as db:db.get(FirmSettings,1).mandate_two_factor=True;db.commit()
        login=client.post('/auth/login',json={'email':email,'password':password})
        assert login.status_code==200,login.text
        fresh={'Authorization':'Bearer '+login.json()['access_token'],'Origin':'https://testserver'}
        begin=client.post('/auth/webauthn/register/begin',headers=fresh)
        assert begin.status_code==200,begin.text


def test_concurrent_admin_resets_do_not_lose_revocation_versions(sample):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    s=sample;barrier=Barrier(2)
    with SessionLocal() as db:before=db.get(User,uuid.UUID(s['staff'])).auth_token_version
    def reset(_):
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return client.post('/admin/users/'+s['staff']+'/disable-2fa',headers=s['admin_headers']).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(reset,range(2)))==[204,204]
    with SessionLocal() as db:assert db.get(User,uuid.UUID(s['staff'])).auth_token_version==before+2
