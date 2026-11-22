import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
import pyotp
import pytest
from fastapi.testclient import TestClient
from passlib.hash import pbkdf2_sha256
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import User,TotpReplayState,FirmSettings
from app.security import hash_password,verify_and_upgrade_password,create_access_token
from app.totp_secrets import encrypt_totp_secret
from tests.ledger_test_helpers import add_user
from tests.test_permission_boundaries_postgres import sample

PASSWORD='Synthetic-password-47!'
NOW=1800000010
@pytest.fixture
def clock(monkeypatch):
    from app import totp_replay
    monkeypatch.setattr(totp_replay,'time',SimpleNamespace(time=lambda:NOW))


def account(db,rounds=600000,enabled=False):
    u=add_user(db,email=uuid.uuid4().hex+'@example.com')
    u.password_hash=pbkdf2_sha256.using(rounds=rounds).hash(PASSWORD)
    secret=pyotp.random_base32();u.totp_secret=encrypt_totp_secret(secret);u.is_2fa_enabled=enabled
    db.get(FirmSettings,1).mandate_two_factor=False;db.get(FirmSettings,1).mandate_password_rotation=False
    db.commit();return u,secret


def test_explicit_hash_cost_and_no_downgrade():
    assert pbkdf2_sha256.from_string(hash_password(PASSWORD)).rounds==600000
    higher=pbkdf2_sha256.using(rounds=650000).hash(PASSWORD)
    assert verify_and_upgrade_password(PASSWORD,higher)==(True,None)


def test_successful_login_upgrades_legacy_hash_without_changing_session_version(db):
    u,_=account(db,rounds=29000);uid=u.id;before=u.auth_token_version
    with TestClient(app) as client:
        assert client.post('/auth/login',json={'email':u.email,'password':'wrong'}).status_code==401
        db.refresh(u);assert pbkdf2_sha256.from_string(u.password_hash).rounds==29000
        response=client.post('/auth/login',json={'email':u.email,'password':PASSWORD})
        assert response.status_code==200,response.text
    db.expire_all();u=db.get(User,uid)
    assert pbkdf2_sha256.from_string(u.password_hash).rounds==600000
    assert u.auth_token_version==before


def test_failed_mfa_does_not_upgrade_hash(db,clock):
    u,secret=account(db,rounds=29000,enabled=True)
    with TestClient(app) as client:assert client.post('/auth/login',json={'email':u.email,'password':PASSWORD,'totp_code':'not-a-code'}).status_code==401
    db.refresh(u);assert pbkdf2_sha256.from_string(u.password_hash).rounds==29000

@pytest.mark.parametrize('offset',[-1,0,1])
def test_drift_code_accepted_once_across_database_sessions(db,clock,offset):
    from app.totp_replay import consume_totp
    secret=pyotp.random_base32();code=pyotp.TOTP(secret).at(NOW+offset*30)
    with SessionLocal() as first:
        assert consume_totp(first,secret=secret,code=code);first.commit()
    with SessionLocal() as second:assert not consume_totp(second,secret=secret,code=code)


def test_replay_claim_rolls_back_with_failed_operation(db,clock):
    from app.totp_replay import consume_totp
    secret=pyotp.random_base32();code=pyotp.TOTP(secret).at(NOW)
    with SessionLocal() as first:assert consume_totp(first,secret=secret,code=code);first.rollback()
    with SessionLocal() as second:assert consume_totp(second,secret=secret,code=code);second.commit()

@pytest.mark.parametrize('master',[False,True])
def test_concurrent_login_code_can_succeed_only_once(db,clock,monkeypatch,master):
    user,secret=account(db,enabled=True);email=user.email
    if master:
        email='isolated-replay-master'
        for key,value in {'MASTER_ADMIN_LOGIN':email,'MASTER_ADMIN_PASSWORD':PASSWORD,'MASTER_ADMIN_REQUIRE_2FA':'true','MASTER_ADMIN_TOTP_SECRET':secret}.items():monkeypatch.setenv(key,value)
    payload={'email':email,'password':PASSWORD,'totp_code':pyotp.TOTP(secret).at(NOW)}
    barrier=Barrier(2)
    def attempt(_):
        with TestClient(app) as client:
            barrier.wait(timeout=10);return client.post('/auth/login',json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==[200,401]
    with TestClient(app) as client:assert client.post('/auth/login',json=payload).status_code==401


def test_enrollment_code_cannot_be_replayed_for_login_or_disable(db,clock):
    u,secret=account(db);code=pyotp.TOTP(secret).at(NOW)
    header={'Authorization':'Bearer '+create_access_token(user_id=str(u.id),role=u.role.value,auth_token_version=u.auth_token_version,mfa_verified=False)}
    with TestClient(app) as client:
        enrolled=client.post('/auth/2fa/verify',json={'code':code},headers=header)
        assert enrolled.status_code==200,enrolled.text
        header={'Authorization':'Bearer '+enrolled.json()['access_token']}
        assert client.post('/auth/login',json={'email':u.email,'password':PASSWORD,'totp_code':code}).status_code==401
        denied=client.post('/auth/2fa/disable',json={'password':PASSWORD,'totp_code':code},headers=header)
        assert denied.status_code==400,denied.text


def test_future_used_step_rejects_older_code_but_accepts_next(db,clock,monkeypatch):
    from app import totp_replay
    secret=pyotp.random_base32();totp=pyotp.TOTP(secret)
    assert totp_replay.consume_totp(db,secret=secret,code=totp.at(NOW+30));db.commit()
    assert not totp_replay.consume_totp(db,secret=secret,code=totp.at(NOW))
    monkeypatch.setattr(totp_replay,'time',SimpleNamespace(time=lambda:NOW+60))
    assert totp_replay.consume_totp(db,secret=secret,code=totp.at(NOW+60));db.commit()


def test_matching_code_collision_cannot_replay_in_later_window(db,clock,monkeypatch):
    from app import totp_replay
    current=NOW//30
    class CollidingTotp:
        interval=30
        def __init__(self,secret):pass
        def generate_otp(self,step):return '123456' if step in (current,current+2) else '654321'
    monkeypatch.setattr(totp_replay.pyotp,'TOTP',CollidingTotp)
    secret=uuid.uuid4().hex
    assert totp_replay.consume_totp(db,secret=secret,code='123456');db.commit()
    monkeypatch.setattr(totp_replay,'time',SimpleNamespace(time=lambda:NOW+30))
    assert not totp_replay.consume_totp(db,secret=secret,code='123456')
