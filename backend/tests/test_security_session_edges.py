"""Authorization boundaries backed by the isolated PostgreSQL database."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select
from app.db import SessionLocal
from app.models import MailPluginAuthCode
from app.mail_plugin_auth_service import exchange_plugin_auth_code, utcnow
from app.security import decode_access_token
from tests.test_high_priority_security import approval, request_for
from tests.ledger_test_helpers import add_user

@pytest.mark.parametrize('invalid',['expired','disabled','legacy','wrong_code','wrong_state','wrong_client'])
def test_invalid_approval_rejected(db,monkeypatch,invalid):
    user,state,code=approval(db,monkeypatch)
    row=db.scalar(select(MailPluginAuthCode).where(MailPluginAuthCode.user_id==user.id))
    if invalid=='expired':row.expires_at=utcnow()-timedelta(seconds=1)
    if invalid=='disabled':user.is_active=False
    if invalid=='legacy':row.auth_token_version=None
    db.commit()
    with pytest.raises(HTTPException) as error:
        exchange_plugin_auth_code(db,client='thunderbird' if invalid=='wrong_client' else 'outlook',
            state=uuid.uuid4().hex if invalid=='wrong_state' else state,
            code='wrong' if invalid=='wrong_code' else code)
    assert error.value.status_code==401

def test_concurrent_redemption_mints_one_token(db,monkeypatch):
    user,state,code=approval(db,monkeypatch)
    barrier=Barrier(2)
    def redeem():
        with SessionLocal() as session:
            barrier.wait(timeout=10)
            try:
                token=exchange_plugin_auth_code(session,client='outlook',state=state,code=code)
                session.commit()
                assert decode_access_token(token).user_id==str(user.id)
                return 200
            except HTTPException as error:
                session.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _:redeem(),range(2)))==[200,401]

@pytest.mark.parametrize('endpoint',['totp','passkey_begin','passkey_finish'])
def test_existing_factor_blocks_unverified_enrollment(db,endpoint):
    from app.routers import auth,webauthn
    user=add_user(db,email=uuid.uuid4().hex+'@example.com')
    user.is_2fa_enabled=True;db.commit()
    request=request_for(user,mfa=False)
    with pytest.raises(HTTPException) as error:
        if endpoint=='totp':auth.setup_2fa(request,user=user,db=db)
        elif endpoint=='passkey_begin':webauthn.webauthn_register_begin(request,user,db)
        else:webauthn.webauthn_register_finish(webauthn.WebAuthnRegisterFinishIn(credential={}),request,Response(),user,db)
    assert error.value.status_code==403

def test_successful_passkey_enrollment_revokes_old_session(db,monkeypatch):
    from app.routers import webauthn
    from app.session_security import lock_current_staff_session
    user=add_user(db,email=uuid.uuid4().hex+'@example.com');db.commit()
    request=request_for(user,mfa=False);before=user.auth_token_version
    webauthn._store_challenge(db,kind='register_begin',subject=str(user.id),challenge=b'synthetic')
    # Crypto verification is mocked; this test covers the surrounding session transaction.
    monkeypatch.setattr(webauthn,'parse_registration_credential_json',lambda _:object())
    monkeypatch.setattr(webauthn,'verify_registration_response',lambda **_:SimpleNamespace(
        credential_id=uuid.uuid4().bytes,credential_public_key=b'synthetic',sign_count=0))
    result=webauthn.webauthn_register_finish(webauthn.WebAuthnRegisterFinishIn(credential={}),request,Response(),user,db)
    assert decode_access_token(result.access_token).auth_token_version==before+1
    assert decode_access_token(result.access_token).mfa_verified is True
    with pytest.raises(HTTPException) as error:lock_current_staff_session(request,user,db)
    assert error.value.status_code==401
