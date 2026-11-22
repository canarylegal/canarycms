"""Recheck security-changing requests after acquiring the staff row lock."""
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.deps import _jwt_raw_from_request
from app.models import User
from app.org_security import user_has_any_passkey
from app.security import decode_access_token


def lock_current_staff_session(request: Request, user: User, db: Session, *, enrolling=False):
    scheme, token = get_authorization_scheme_param(request.headers.get("authorization"))
    creds = HTTPAuthorizationCredentials(scheme=scheme, credentials=token) if scheme.lower() == "bearer" and token else None
    raw = _jwt_raw_from_request(request, creds)
    try:
        claims = decode_access_token(raw or "")
    except ValueError as exc:
        raise HTTPException(401, "Session expired — sign in again.") from exc
    current = db.execute(select(User).where(User.id == user.id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if (current is None or not current.is_active or claims.user_id != str(current.id)
            or claims.auth_token_version is None
            or claims.auth_token_version != int(current.auth_token_version)):
        raise HTTPException(401, "Session expired — sign in again.")
    if (enrolling and (current.is_2fa_enabled or user_has_any_passkey(db, current.id))
            and claims.mfa_verified is not True):
        raise HTTPException(403, "Verify your existing authenticator or passkey before adding another sign-in method.")
    return current, claims
