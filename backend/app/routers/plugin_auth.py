"""Authorize Thunderbird / Outlook mail add-ins via browser login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.client_ip import client_ip_from_request
from app.db import get_db
from app.deps import _jwt_raw_from_request, get_current_user
from app.mail_plugin_auth_service import create_plugin_auth_code, exchange_plugin_auth_code
from app.models import User
from app.schemas import PluginAuthorizeIn, PluginAuthorizeOut, PluginTokenIn, TokenResponse
from app.master_admin import MASTER_RECOVERY_ROLE
from app.security import decode_access_token
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

router = APIRouter(prefix="/auth/plugin", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


def _require_verified_staff(user: User, request: Request, creds: HTTPAuthorizationCredentials | None) -> None:
    raw = _jwt_raw_from_request(request, creds)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_access_token(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if payload.role == MASTER_RECOVERY_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The master recovery account cannot authorize mail add-ins.",
        )
    if payload.mfa_verified is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Complete sign-in with passkey or authenticator app before authorizing the mail add-in."
            ),
        )
    if payload.password_ok is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Change your password in Canary before authorizing the mail add-in.",
        )


@router.post("/authorize", response_model=PluginAuthorizeOut)
def authorize_plugin(
    payload: PluginAuthorizeIn,
    request: Request,
    user: User = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> PluginAuthorizeOut:
    _require_verified_staff(user, request, creds)
    code = create_plugin_auth_code(
        db,
        user=user,
        client=payload.client,
        state=payload.state,
        redirect_uri=payload.redirect_uri,
    )
    db.commit()
    return PluginAuthorizeOut(code=code)


@router.post("/token", response_model=TokenResponse)
def exchange_plugin_token(
    payload: PluginTokenIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    _ = client_ip_from_request(request)
    token = exchange_plugin_auth_code(
        db,
        client=payload.client,
        state=payload.state,
        code=payload.code,
    )
    db.commit()
    return TokenResponse(access_token=token)
