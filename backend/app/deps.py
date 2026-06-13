from __future__ import annotations

import logging
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_access import user_effective_admin
from app.auth_principal import AuthPrincipal
from app.db import get_db
from app.master_admin import MASTER_RECOVERY_ROLE, MASTER_RECOVERY_USER_ID
from app.models import Case, CaseAccessMode, CaseAccessRule, CaseLockMode, Contact, User
from app.org_security import firm_mandates_second_factor, user_meets_second_factor_policy
from app.org_security import user_password_change_required
from app.security import decode_access_token
from app.permission_checks import user_may_be_fee_earner

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

_SECOND_FACTOR_SETUP_PATH_EXACT = frozenset(
    {
        "/auth/me",
        "/auth/change-password",
    }
)
_PASSWORD_CHANGE_PATH_EXACT = frozenset(
    {
        "/auth/me",
        "/auth/change-password",
    }
)
_SECOND_FACTOR_SETUP_PREFIXES = (
    "/auth/2fa/",
    "/auth/webauthn/register",
    "/auth/webauthn/credentials",
)


def _path_allows_second_factor_setup(path: str) -> bool:
    if path in _SECOND_FACTOR_SETUP_PATH_EXACT:
        return True
    return any(path.startswith(p) for p in _SECOND_FACTOR_SETUP_PREFIXES)


def _path_allows_password_change_only(path: str) -> bool:
    return path in _PASSWORD_CHANGE_PATH_EXACT


def _jwt_raw_from_request(request: Request, creds: HTTPAuthorizationCredentials | None) -> str | None:
    """Prefer ``Authorization: Bearer``, then ``X-Canary-Token`` (some proxies strip Bearer on multipart POST)."""

    if creds is not None and creds.scheme.lower() == "bearer":
        c = (creds.credentials or "").strip()
        if c:
            return c
    alt = request.headers.get("x-canary-token")
    if alt:
        t = alt.strip()
        if t:
            return t
    return None


def get_auth_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    raw = _jwt_raw_from_request(request, creds)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    try:
        payload = decode_access_token(raw)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.role == MASTER_RECOVERY_ROLE:
        if payload.user_id != MASTER_RECOVERY_USER_ID:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return AuthPrincipal(is_master_recovery=True, user=None)

    try:
        user_uuid = uuid.UUID(payload.user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.get(User, user_uuid)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")

    if not user_effective_admin(user, db):
        if user_password_change_required(db, user) and not _path_allows_password_change_only(request.url.path):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your password has expired under your organisation's security policy. "
                    "Choose a new password before using Canary."
                ),
            )

    if firm_mandates_second_factor(db):
        db_ok = user_meets_second_factor_policy(db, user.id, is_2fa_enabled=user.is_2fa_enabled)
        if not db_ok:
            if not _path_allows_second_factor_setup(request.url.path):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your organisation requires two-factor authentication (authenticator app) or a registered passkey. "
                        "Finish the security setup screen first — you cannot use the rest of Canary until enrolment is complete."
                    ),
                )
        elif payload.mfa_verified is not True:
            if not _path_allows_second_factor_setup(request.url.path):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your organisation requires a verified second factor at sign-in. "
                        "Use Sign in with passkey, or sign in with password and enter your authenticator code when prompted."
                    ),
                )
    return AuthPrincipal(is_master_recovery=False, user=user)


def get_current_user(principal: AuthPrincipal = Depends(get_auth_principal)) -> User:
    if principal.is_master_recovery or principal.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a firm staff account.",
        )
    return principal.user


def require_firm_admin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not user_effective_admin(user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


# Historical name used across admin routers (firm DB admin only — not master recovery).
require_admin = require_firm_admin


def require_recovery_operator(
    principal: AuthPrincipal = Depends(get_auth_principal),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    if principal.is_master_recovery:
        return principal
    if principal.user and user_effective_admin(principal.user, db):
        return principal
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")


def require_case_access(case_id, user: User, db: Session) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    if user_effective_admin(user, db):
        return case

    if case.fee_earner_user_id and user.id == case.fee_earner_user_id and user_may_be_fee_earner(user, db):
        return case

    if case.lock_mode == CaseLockMode.none:
        return case

    rules = (
        db.execute(select(CaseAccessRule).where(CaseAccessRule.case_id == case_id, CaseAccessRule.user_id == user.id))
        .scalars()
        .all()
    )
    mode = case.lock_mode

    if mode == CaseLockMode.allow_list:
        if any(r.mode == CaseAccessMode.allow for r in rules):
            return case
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This matter uses restricted access; you are not on the allowed list.",
        )

    if mode == CaseLockMode.open_by_default:
        if any(r.mode == CaseAccessMode.deny for r in rules):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to this matter has been revoked for your user.")
        return case

    return case


def get_case_if_accessible(case_id: uuid.UUID, user: User, db: Session) -> Case | None:
    """Return the matter if ``user`` may access it; ``None`` if missing or denied (no exception)."""
    case = db.get(Case, case_id)
    if not case:
        return None

    if user_effective_admin(user, db):
        return case

    if case.fee_earner_user_id and user.id == case.fee_earner_user_id and user_may_be_fee_earner(user, db):
        return case

    if case.lock_mode == CaseLockMode.none:
        return case

    rules = (
        db.execute(select(CaseAccessRule).where(CaseAccessRule.case_id == case_id, CaseAccessRule.user_id == user.id))
        .scalars()
        .all()
    )
    mode = case.lock_mode

    if mode == CaseLockMode.allow_list:
        if any(r.mode == CaseAccessMode.allow for r in rules):
            return case
        return None

    if mode == CaseLockMode.open_by_default:
        if any(r.mode == CaseAccessMode.deny for r in rules):
            return None
        return case

    return None


def get_portal_contact(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Contact:
    from app.models import ContactPortalAccess
    from app.portal_service import portal_access_is_active
    from app.security import decode_portal_session_token

    raw = _jwt_raw_from_request(request, creds)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing portal session")
    try:
        payload = decode_portal_session_token(raw)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired portal session")
    try:
        contact_id = uuid.UUID(payload.contact_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal session")
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal session")
    access = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access is None or not portal_access_is_active(access):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal access is disabled")
    return contact
