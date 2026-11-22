"""Synthetic regressions for the high-priority trust-boundary review."""
import uuid
import pyotp
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request
from app.db import SessionLocal
from app.models import UserRole
from app.security import create_access_token, decode_access_token, hash_password
from app.totp_secrets import encrypt_totp_secret
from tests.ledger_test_helpers import add_user, add_case, add_fee_earner_category


def request_for(user, *, mfa=True):
    token=create_access_token(user_id=str(user.id),role=user.role.value,
        auth_token_version=user.auth_token_version,mfa_verified=mfa)
    return Request({'type':'http','method':'POST','path':'/auth/test','scheme':'https',
        'server':('test',443),'headers':[(b'origin',b'https://test'),(b'host',b'test'),(b'authorization',('Bearer '+token).encode())]})


def approval(db,monkeypatch):
    from app.mail_plugin_auth_service import create_plugin_auth_code
    monkeypatch.setenv('CANARY_PUBLIC_URL','https://canary.example.com')
    user=add_user(db,email=uuid.uuid4().hex+'@example.com')
    state=uuid.uuid4().hex
    code=create_plugin_auth_code(db,user=user,client='outlook',state=state,
        redirect_uri='https://canary.example.com/outlook-addin/auth-callback.html')
    db.commit()
    return user,state,code


def test_state_only_plugin_exchange_is_rejected(db,monkeypatch):
    from app.mail_plugin_auth_service import exchange_plugin_auth_code
    user,state,code=approval(db,monkeypatch)
    with pytest.raises(HTTPException) as error:
        exchange_plugin_auth_code(db,client='outlook',state=state)
    assert error.value.status_code==401


def test_thunderbird_callback_must_not_leave_configured_origin(monkeypatch):
    from app.mail_plugin_auth_service import validate_plugin_redirect_uri
    monkeypatch.setenv('CANARY_PUBLIC_URL','https://canary.example.com')
    with pytest.raises(HTTPException) as error:
        validate_plugin_redirect_uri('thunderbird','https://attacker.example/connect/mail-plugin/callback')
    assert error.value.status_code==400


def test_unredeemed_approval_does_not_survive_session_revocation(db,monkeypatch):
    from app.mail_plugin_auth_service import exchange_plugin_auth_code
    from app.security import bump_auth_token_version
    user,state,code=approval(db,monkeypatch)
    bump_auth_token_version(user);db.commit()
    with pytest.raises(HTTPException) as error:
        exchange_plugin_auth_code(db,client='outlook',state=state,code=code)
    assert error.value.status_code==401


def test_password_change_preserves_unverified_factor_claim(db):
    from app.routers.auth import change_password
    from app.schemas import ChangePasswordRequest
    user=add_user(db,email=uuid.uuid4().hex+'@example.com')
    user.password_hash=hash_password('Synthetic-old-password-71!');db.commit()
    before=user.auth_token_version
    result=change_password(ChangePasswordRequest(current_password='Synthetic-old-password-71!',
        new_password='Synthetic-new-password-84!'),request_for(user,mfa=False),Response(),user,db)
    claims=decode_access_token(result.access_token)
    assert claims.mfa_verified is False
    assert claims.auth_token_version==before+1


def test_totp_enrollment_revokes_pre_enrollment_sessions(db):
    from app.routers.auth import verify_2fa
    from app.schemas import Verify2FARequest
    user=add_user(db,email=uuid.uuid4().hex+'@example.com')
    secret=pyotp.random_base32();user.totp_secret=encrypt_totp_secret(secret);db.commit()
    before=user.auth_token_version
    result=verify_2fa(Verify2FARequest(code=pyotp.TOTP(secret).now()),request_for(user,mfa=False),Response(),user,db)
    assert user.auth_token_version==before+1
    assert decode_access_token(result.access_token).mfa_verified is True


def test_busy_pending_invoice_pair_must_not_be_voided(db):
    from app.invoice_service import create_case_invoice,void_case_invoice
    from app.ledger_service import _try_lock_ledger_pair
    from tests.test_invoice_service import _invoice_payload
    user=add_user(db,email=uuid.uuid4().hex+'@example.com');case=add_case(db,fee_earner_user_id=user.id)
    inv=create_case_invoice(case.id,_invoice_payload(credit_user_id=user.id),user,db);db.commit()
    with SessionLocal() as locker:
        _try_lock_ledger_pair(locker,inv.ledger_pair_id)
        with pytest.raises(HTTPException) as error:void_case_invoice(case.id,inv.id,user,db)
        assert error.value.status_code==409
    db.rollback()
    from app.models import CaseInvoice
    persisted=db.get(CaseInvoice,inv.id)
    assert persisted.status=='pending_approval'


@pytest.mark.parametrize('operation',['preview','list','detail'])
def test_reconciliation_reads_require_accounts_workspace(db,operation):
    from app.routers import reconciliations as router
    from sqlalchemy import select
    from app.models import UserPermissionCategory
    category=db.scalar(select(UserPermissionCategory).where(UserPermissionCategory.name=="Fee earner")) or add_fee_earner_category(db)
    user=add_user(db,role=UserRole.user,permission_category_id=category.id,email=uuid.uuid4().hex+'@example.com')
    with pytest.raises(HTTPException) as error:
        if operation=='preview':router.preview_totals(user,db)
        elif operation=='list':router.list_reconciliation_rows(user,db)
        else:router.get_reconciliation_row(uuid.uuid4(),user,db)
    assert error.value.status_code==403
