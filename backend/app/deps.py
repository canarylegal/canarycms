from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Case, CaseAccessMode, CaseAccessRule, CaseLockMode, User
from app.security import decode_access_token
from app.admin_access import user_effective_admin


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    try:
        payload = decode_access_token(creds.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.get(User, payload.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")
    return user


def require_admin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not user_effective_admin(user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


def require_case_access(case_id, user: User, db: Session) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    if user_effective_admin(user, db):
        return case

    if case.fee_earner_user_id and user.id == case.fee_earner_user_id:
        return case

    if case.lock_mode == CaseLockMode.none:
        return case

    rules = (
        db.execute(select(CaseAccessRule).where(CaseAccessRule.case_id == case_id, CaseAccessRule.user_id == user.id))
        .scalars()
        .all()
    )
    mode = case.lock_mode

    # Allow-list mode (stored as ``blacklist``): only fee earner, admins, and explicitly allowed users.
    if mode == CaseLockMode.blacklist:
        if any(r.mode == CaseAccessMode.allow for r in rules):
            return case
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This matter uses restricted access; you are not on the allowed list.",
        )

    # Open-by-default mode (stored as ``whitelist``): everyone may access unless explicitly denied.
    if mode == CaseLockMode.whitelist:
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

    if case.fee_earner_user_id and user.id == case.fee_earner_user_id:
        return case

    if case.lock_mode == CaseLockMode.none:
        return case

    rules = (
        db.execute(select(CaseAccessRule).where(CaseAccessRule.case_id == case_id, CaseAccessRule.user_id == user.id))
        .scalars()
        .all()
    )
    mode = case.lock_mode

    if mode == CaseLockMode.blacklist:
        if any(r.mode == CaseAccessMode.allow for r in rules):
            return case
        return None

    if mode == CaseLockMode.whitelist:
        if any(r.mode == CaseAccessMode.deny for r in rules):
            return None
        return case

    return case

