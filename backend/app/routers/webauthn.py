"""WebAuthn / passkey registration (authenticated) and login (public)."""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.parse_authentication_credential_json import parse_authentication_credential_json
from webauthn.helpers.parse_registration_credential_json import parse_registration_credential_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user
from app.models import User, WebAuthnChallenge, WebAuthnCredential
from app.org_security import firm_mandates_second_factor
from app.password_reset_service import login_access_token
from app.security import create_access_token
from app.schemas import TokenResponse

router = APIRouter(prefix="/auth/webauthn", tags=["webauthn"])
log = logging.getLogger(__name__)

_CHALLENGE_TTL = timedelta(minutes=5)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _rp_name() -> str:
    return (os.getenv("WEBAUTHN_RP_NAME") or "Canary").strip() or "Canary"


def _rp_id_for_request(request: Request) -> str:
    explicit = (os.getenv("WEBAUTHN_RP_ID") or "").strip()
    if explicit:
        return explicit
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    return host or "localhost"


def _expected_origin(request: Request) -> str:
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        return origin.rstrip("/")
    ref = (request.headers.get("referer") or "").strip()
    if ref:
        try:
            from urllib.parse import urlparse

            u = urlparse(ref)
            if u.scheme and u.netloc:
                return f"{u.scheme}://{u.netloc}".rstrip("/")
        except Exception:
            pass
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Missing Origin header — WebAuthn requires a browser origin.",
    )


def _purge_expired_challenges(db: Session) -> None:
    now = datetime.now(timezone.utc)
    db.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < now))


def _store_challenge(db: Session, *, kind: str, subject: str, challenge: bytes) -> None:
    _purge_expired_challenges(db)
    db.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.kind == kind, WebAuthnChallenge.subject == subject))
    row = WebAuthnChallenge(
        id=uuid.uuid4(),
        kind=kind,
        subject=subject,
        challenge_b64=_b64url_encode(challenge),
        expires_at=datetime.now(timezone.utc) + _CHALLENGE_TTL,
    )
    db.add(row)
    db.commit()


def _pop_challenge(db: Session, *, kind: str, subject: str) -> bytes:
    now = datetime.now(timezone.utc)
    row = (
        db.execute(
            select(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.kind == kind,
                WebAuthnChallenge.subject == subject,
                WebAuthnChallenge.expires_at >= now,
            )
            .order_by(WebAuthnChallenge.expires_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="WebAuthn challenge expired or missing.")
    db.delete(row)
    db.commit()
    return base64url_to_bytes(row.challenge_b64)


class WebAuthnLoginBeginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class WebAuthnLoginFinishIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    credential: dict[str, Any]


class WebAuthnRegisterFinishIn(BaseModel):
    credential: dict[str, Any]
    label: str | None = Field(default=None, max_length=200)


class WebAuthnCredentialOut(BaseModel):
    id: uuid.UUID
    label: str | None
    transports: str | None
    created_at: datetime


@router.post("/login/begin")
def webauthn_login_begin(
    payload: WebAuthnLoginBeginIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    email = str(payload.email).lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    creds = db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)).scalars().all()
    if not creds:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No passkeys registered for this account.")

    rp_id = _rp_id_for_request(request)
    allow = [PublicKeyCredentialDescriptor(id=c.credential_id) for c in creds]
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store_challenge(db, kind="login_begin", subject=email, challenge=options.challenge)
    return json.loads(options_to_json(options))


@router.post("/login/finish", response_model=TokenResponse)
def webauthn_login_finish(
    payload: WebAuthnLoginFinishIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(payload.email).lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    expected_challenge = _pop_challenge(db, kind="login_begin", subject=email)
    rp_id = _rp_id_for_request(request)
    origin = _expected_origin(request)

    auth_cred = parse_authentication_credential_json(json.dumps(payload.credential))

    raw_id = auth_cred.raw_id
    cred_row = (
        db.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.credential_id == raw_id,
            )
        )
        .scalars()
        .first()
    )
    if cred_row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown passkey.")

    verification = verify_authentication_response(
        credential=auth_cred,
        expected_challenge=expected_challenge,
        expected_origin=origin,
        expected_rp_id=rp_id,
        credential_public_key=cred_row.public_key,
        credential_current_sign_count=cred_row.sign_count,
        require_user_verification=False,
    )

    cred_row.sign_count = verification.new_sign_count
    db.add(cred_row)
    db.commit()

    token = login_access_token(db, user, mfa_verified=True)
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.login.passkey",
        entity_type="user",
        entity_id=str(user.id),
        meta={"email": user.email},
    )
    return TokenResponse(access_token=token)


@router.post("/register/begin")
def webauthn_register_begin(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    rp_id = _rp_id_for_request(request)
    existing = db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)).scalars().all()
    exclude = [PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing]

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=_rp_name(),
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.display_name,
        exclude_credentials=exclude or None,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _store_challenge(db, kind="register_begin", subject=str(user.id), challenge=options.challenge)
    return json.loads(options_to_json(options))


@router.post("/register/finish", response_model=TokenResponse)
def webauthn_register_finish(
    payload: WebAuthnRegisterFinishIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    expected_challenge = _pop_challenge(db, kind="register_begin", subject=str(user.id))
    rp_id = _rp_id_for_request(request)
    origin = _expected_origin(request)

    reg_cred = parse_registration_credential_json(json.dumps(payload.credential))
    verification = verify_registration_response(
        credential=reg_cred,
        expected_challenge=expected_challenge,
        expected_origin=origin,
        expected_rp_id=rp_id,
        require_user_verification=False,
    )

    cred_id = verification.credential_id
    dup = db.execute(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == cred_id)).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This passkey is already registered.")

    transports = payload.credential.get("response", {}).get("transports")
    transports_s = ",".join(transports) if isinstance(transports, list) else None

    row = WebAuthnCredential(
        id=uuid.uuid4(),
        user_id=user.id,
        credential_id=cred_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        transports=transports_s,
        label=(payload.label or "").strip() or None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.webauthn.register",
        entity_type="user",
        entity_id=str(user.id),
        meta={"credential_id_prefix": _b64url_encode(cred_id)[:16]},
    )
    access_token = create_access_token(user_id=str(user.id), role=user.role.value, mfa_verified=True)
    return TokenResponse(access_token=access_token)


@router.get("/credentials", response_model=list[WebAuthnCredentialOut])
def list_my_passkeys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WebAuthnCredentialOut]:
    rows = db.execute(select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)).scalars().all()
    return [
        WebAuthnCredentialOut(id=r.id, label=r.label, transports=r.transports, created_at=r.created_at) for r in rows
    ]


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_passkey(
    credential_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(WebAuthnCredential, credential_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")

    others = (
        db.execute(
            select(WebAuthnCredential.id).where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.id != credential_id,
            )
        )
        .scalars()
        .all()
    )
    if firm_mandates_second_factor(db) and not user.is_2fa_enabled and len(others) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your organisation requires two-factor authentication or at least one passkey.",
        )

    db.delete(row)
    db.commit()
    log_event(
        db,
        actor_user_id=user.id,
        action="auth.webauthn.delete",
        entity_type="user",
        entity_id=str(user.id),
        meta={"credential_row_id": str(credential_id)},
    )
    return None
