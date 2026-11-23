"""Mail add-in sessions follow firm policy without upgrading factor claims."""
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,FirmSettings
from app.security import create_access_token,decode_access_token,hash_password
from tests.test_permission_boundaries_postgres import sample

@pytest.fixture(autouse=True)
def public_origin(monkeypatch):
    monkeypatch.setenv('CANARY_PUBLIC_URL','https://canary.example.com')
    yield
    with SessionLocal() as db:
        settings=db.get(FirmSettings,1)
        if settings:settings.mandate_two_factor=False;db.commit()

def headers(sample,verified):
    with SessionLocal() as db:user=db.get(User,uuid.UUID(sample['admin']));version=user.auth_token_version
    return {'Authorization':'Bearer '+create_access_token(user_id=sample['admin'],role='admin',auth_token_version=version,mfa_verified=verified)}

def body(client):
    return {'client':client,'state':uuid.uuid4().hex,'redirect_uri':'https://canary.example.com'+('/connect/mail-plugin/callback' if client=='thunderbird' else '/outlook-addin/auth-callback.html')}

@pytest.mark.parametrize('client',['thunderbird','outlook'])
@pytest.mark.parametrize('verified',[False,True,None])
def test_optional_factor_authorization_preserves_session_claim(sample,client,verified):
    h=headers(sample,verified);payload=body(client)
    with TestClient(app) as c:
        assert c.get('/auth/me',headers=h).json()['session_second_factor_verified'] is True
        response=c.post('/auth/plugin/authorize',headers=h,json=payload);assert response.status_code==200,response.text
        exchanged=c.post('/auth/plugin/token',json={'client':client,'state':payload['state'],'code':response.json()['code']});assert exchanged.status_code==200,exchanged.text
        token=exchanged.json()['access_token'];assert decode_access_token(token).mfa_verified is (verified is True)
        assert c.get('/auth/me',headers={'Authorization':'Bearer '+token}).status_code==200

@pytest.mark.parametrize('client',['thunderbird','outlook'])
def test_normal_password_login_without_enrollment_can_connect(sample,client):
    with SessionLocal() as db:
        user=db.get(User,uuid.UUID(sample['admin']));user.password_hash=hash_password('Synthetic-password-72!');email=user.email;db.commit()
    with TestClient(app) as c:
        login=c.post('/auth/login',json={'email':email,'password':'Synthetic-password-72!'});assert login.status_code==200,login.text
        result=c.post('/auth/plugin/authorize',headers={'Authorization':'Bearer '+login.json()['access_token']},json=body(client));assert result.status_code==200,result.text

@pytest.mark.parametrize('client',['thunderbird','outlook'])
@pytest.mark.parametrize('enrolled,verified,expected',[(False,False,403),(True,False,403),(True,True,200)])
def test_mandatory_factor_policy_still_enforced(sample,client,enrolled,verified,expected):
    with SessionLocal() as db:
        db.get(FirmSettings,1).mandate_two_factor=True;db.get(User,uuid.UUID(sample['admin'])).is_2fa_enabled=enrolled;db.commit()
    with TestClient(app) as c:
        response=c.post('/auth/plugin/authorize',headers=headers(sample,verified),json=body(client));assert response.status_code==expected,response.text

@pytest.mark.parametrize('client',['thunderbird','outlook'])
def test_policy_change_before_redemption_rejects_unverified_approval(sample,client):
    payload=body(client)
    with TestClient(app) as c:
        approval=c.post('/auth/plugin/authorize',headers=headers(sample,False),json=payload);assert approval.status_code==200
        with SessionLocal() as db:db.get(FirmSettings,1).mandate_two_factor=True;db.commit()
        result=c.post('/auth/plugin/token',json={'client':client,'state':payload['state'],'code':approval.json()['code']});assert result.status_code==403,result.text
