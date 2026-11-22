"""Real signed synthetic ES256 assertions, independent PostgreSQL sessions, no services."""
import base64
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException, Response
from sqlalchemy import delete, select
from starlette.requests import Request
from app.db import SessionLocal
from app.models import AuthRateLimitEntry, WebAuthnChallenge, WebAuthnCredential
from app.routers import webauthn as w
from app.security import create_access_token, decode_access_token
from tests.ledger_test_helpers import add_user


def request(ip='192.0.2.1', token=None, origin='https://canary.test', forwarded=None):
    headers=[(b'host', b'canary.test'), (b'origin', origin.encode())]
    if token: headers.append((b'authorization', ('Bearer '+token).encode()))
    if forwarded: headers.append((b'x-forwarded-for', forwarded.encode()))
    return Request({'type':'http','method':'POST','path':'/auth/webauthn/login/begin',
        'headers':headers,'client':(ip,1234),'scheme':'https','server':('canary.test',443)})


@pytest.fixture(autouse=True)
def budgets(db, monkeypatch):
    monkeypatch.setenv('WEBAUTHN_RP_ID','canary.test')
    db.execute(delete(AuthRateLimitEntry).where(AuthRateLimitEntry.scope.like('webauthn_%')));db.commit()


@pytest.fixture
def identity(db):
    user=add_user(db,email=uuid.uuid4().hex+'@example.test');db.commit()
    key=ec.generate_private_key(ec.SECP256R1());p=key.public_key().public_numbers()
    cred=WebAuthnCredential(id=uuid.uuid4(),user_id=user.id,credential_id=uuid.uuid4().bytes,
        public_key=cbor2.dumps({1:2,3:-7,-1:1,-2:p.x.to_bytes(32,'big'),-3:p.y.to_bytes(32,'big')}),sign_count=0)
    db.add(cred);db.commit()
    return user,key,cred


def begin(db,email,req=None):
    return w.webauthn_login_begin(w.WebAuthnLoginBeginIn(email=email),req or request(),db)


def assertion(identity,options,*,uv=True,handle=True,origin='https://canary.test',rp='canary.test',counter=1):
    user,key,cred=identity
    client=json.dumps({'type':'webauthn.get','challenge':options['challenge'],'origin':origin}).encode()
    data=hashlib.sha256(rp.encode()).digest()+bytes([5 if uv else 1])+counter.to_bytes(4,'big')
    sig=key.sign(data+hashlib.sha256(client).digest(),ec.ECDSA(hashes.SHA256()))
    enc=w._b64url_encode
    return {'id':enc(cred.credential_id),'rawId':enc(cred.credential_id),'type':'public-key',
        'response':{'clientDataJSON':enc(client),'authenticatorData':enc(data),'signature':enc(sig),
            'userHandle':enc(user.id.bytes) if handle else None},'clientExtensionResults':{}}


def finish(db,email,credential,req=None):
    return w.webauthn_login_finish(w.WebAuthnLoginFinishIn(email=email,credential=credential),req or request(),Response(),db)


def rejected(fn):
    with pytest.raises(HTTPException) as error:fn()
    assert error.value.status_code==401
    assert error.value.detail=='Passkey sign-in failed. Start again.'


def test_public_options_identical_for_every_account_state(db,identity):
    user,_,_=identity
    empty=add_user(db,email=uuid.uuid4().hex+'@example.test');db.commit()
    emails=[user.email,empty.email,uuid.uuid4().hex+'@example.test']
    options=[begin(db,email) for email in emails]
    user.is_active=False;db.commit();options.append(begin(db,user.email))
    assert len({o.pop('challenge') for o in options})==4
    assert all(o==options[0] for o in options)
    assert not options[0].get('allowCredentials')
    assert options[0]['userVerification']=='required'


def test_independent_attempts_real_signatures_and_replay(db,identity):
    user,_,cred=identity
    first=begin(db,user.email);second=begin(db,user.email)
    one=assertion(identity,first);two=assertion(identity,second,counter=2)
    assert decode_access_token(finish(db,user.email,one).access_token).mfa_verified is True
    rejected(lambda:finish(db,user.email,one))
    assert decode_access_token(finish(db,user.email,two).access_token).user_id==str(user.id)
    db.refresh(cred);assert cred.sign_count==2


@pytest.mark.parametrize('bad',['signature','origin','rp','no_uv','no_handle','wrong_handle','inactive','deleted_key','expired','malformed','wrong_email','request_origin'])
def test_invalid_assertions_generic_failure(db,identity,bad):
    user,_,cred=identity;options=begin(db,user.email)
    kw={'uv':False} if bad=='no_uv' else {'handle':False} if bad=='no_handle' else {bad:'https://other.test' if bad=='origin' else 'other.test'} if bad in ['origin','rp'] else {}
    signed=assertion(identity,options,**kw)
    if bad=='signature':signed['response']['signature']=w._b64url_encode(b'bad')
    if bad=='wrong_handle':signed['response']['userHandle']=w._b64url_encode(uuid.uuid4().bytes)
    if bad=='inactive':user.is_active=False
    if bad=='deleted_key':db.delete(cred)
    if bad=='expired':
        row=db.get(WebAuthnChallenge,uuid.UUID(bytes=base64.urlsafe_b64decode(options['challenge']+'==')[:16]));row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    if bad=='malformed':signed={}
    db.commit()
    rejected(lambda:finish(db,'unknown@example.test' if bad=='wrong_email' else user.email,signed,
        request(origin='https://other.test') if bad=='request_origin' else None))


def test_legacy_key_after_password_session_and_reset_revocation(db,identity):
    user,_,cred=identity
    token=create_access_token(user_id=str(user.id),role=user.role.value,mfa_verified=False,auth_token_version=user.auth_token_version)
    req=request(token=token)
    options=begin(db,user.email,req)
    assert options['allowCredentials']==[{'id':w._b64url_encode(cred.credential_id),'type':'public-key'}]
    assert options['userVerification']=='preferred'
    assert decode_access_token(finish(db,user.email,assertion(identity,options,uv=False,handle=False)).access_token).mfa_verified is True
    options=begin(db,user.email,req)
    user.auth_token_version+=1;db.commit()
    rejected(lambda:finish(db,user.email,assertion(identity,options,uv=False,handle=False,counter=2)))
    assert not begin(db,user.email,req).get('allowCredentials')


def test_session_cannot_discover_another_account(db,identity):
    user,_,_=identity
    token=create_access_token(user_id=str(user.id),role=user.role.value,auth_token_version=user.auth_token_version)
    assert not begin(db,'someoneelse@example.test',request(token=token)).get('allowCredentials')


@pytest.mark.parametrize('phase',['begin','finish'])
def test_limits_count_all_requests_and_ignore_forwarded_headers(db,identity,monkeypatch,phase):
    monkeypatch.setenv('WEBAUTHN_'+phase.upper()+'_ACCOUNT_IP_MAX_ATTEMPTS','2')
    email=identity[0].email
    def call(ip='192.0.2.1'):
        req=request(ip=ip,forwarded=uuid.uuid4().hex)
        if phase=='begin':return begin(db,email,req)
        try:finish(db,email,{},req)
        except HTTPException as error:
            if error.status_code != 401:raise
    call();call()
    with pytest.raises(HTTPException) as error:call()
    assert error.value.status_code==429 and int(error.value.headers['Retry-After'])>0
    call('192.0.2.2')
    rows=db.scalars(select(AuthRateLimitEntry).where(AuthRateLimitEntry.scope.like('webauthn_%'))).all()
    for row in rows:row.locked_until=datetime.now(timezone.utc)-timedelta(seconds=1)
    db.commit();call()


def test_ip_budget_caps_distinct_unknown_accounts(db,monkeypatch):
    monkeypatch.setenv('WEBAUTHN_BEGIN_IP_MAX_ATTEMPTS','2')
    for i in range(2):begin(db,f'unknown{i}@example.test')
    with pytest.raises(HTTPException) as error:begin(db,'third@example.test')
    assert error.value.status_code==429


def test_concurrent_finish_consumes_challenge_once(db,identity):
    email=identity[0].email;signed=assertion(identity,begin(db,email));barrier=Barrier(2)
    def redeem(_):
        with SessionLocal() as session:
            barrier.wait(timeout=10)
            try:finish(session,email,signed);return 200
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(redeem,range(2)))==[200,401]


def test_concurrent_rate_limit_first_insert_is_atomic(db,monkeypatch):
    monkeypatch.setenv('WEBAUTHN_BEGIN_ACCOUNT_IP_MAX_ATTEMPTS','3');barrier=Barrier(8)
    def call(_):
        with SessionLocal() as session:
            barrier.wait(timeout=10)
            try:begin(session,'unknown@example.test');return 200
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:assert sorted(pool.map(call,range(8)))==[200]*3+[429]*5
