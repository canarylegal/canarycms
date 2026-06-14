import os
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.calendar_service import ensure_default_calendar
from app.case_time_service import user_has_charge_rate
from app.db import get_db
from app.deps import get_current_user
from app.email_crypt import encrypt_password
from app.email_integration_settings import build_user_public
from app.models import User
from app.permission_checks import (
    user_may_access_accounts_workspace,
    user_may_approve_invoice,
    user_may_approve_ledger,
    user_may_be_fee_earner,
)
from app.radicale_htpasswd import remove_user, upsert_user
from app.schemas import (
    LedgerPermissionsOut,
    UserAppearanceUpdate,
    UserCalDAVProvisionOut,
    UserCalDAVStatusOut,
    UserEmailHandlingUpdate,
    UserPublic,
    UserUiPreferencesUpdate,
)
from app.user_appearance import normalize_appearance_update
from app.user_ui_preferences import UserUiPreferencesPatch, merge_ui_preferences_patch, user_ui_preferences_out


router = APIRouter(prefix="/users", tags=["users"])

DEFAULT_OUTLOOK_MAIL_URL = "https://outlook.office.com/mail"


def _validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL must use http:// or https://",
        )
    if not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid URL")
    return url


def _caldav_base_url() -> str:
    return (os.getenv("CANARY_CALDAV_PUBLIC_URL") or "http://localhost:5232").strip().rstrip("/")


def _caldav_principal_url(user_id: uuid.UUID) -> str:
    return f"{_caldav_base_url()}/{user_id}/"


def _caldav_username(user: User) -> str:
    return str(user.id)


class UserSummary(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    initials: str
    role: str
    is_active: bool
    can_be_fee_earner: bool = False
    has_charge_rate: bool = False


@router.get("", response_model=list[UserSummary])
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[UserSummary]:
    users = db.execute(select(User).order_by(User.display_name.asc())).scalars().all()
    return [
        UserSummary(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            initials=u.initials,
            role=u.role.value if hasattr(u.role, "value") else str(u.role),
            is_active=u.is_active,
            can_be_fee_earner=user_may_be_fee_earner(u, db),
            has_charge_rate=user_has_charge_rate(u),
        )
        for u in users
    ]


@router.get("/search", response_model=list[UserSummary])
def search_users(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserSummary]:
    needle = q.strip().lower()
    if not needle:
        return []
    pattern = f"%{needle}%"
    users = (
        db.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                or_(
                    func.lower(User.display_name).like(pattern),
                    func.lower(User.email).like(pattern),
                    func.lower(User.initials).like(pattern),
                ),
            )
            .order_by(User.display_name.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        UserSummary(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            initials=u.initials,
            role=u.role.value if hasattr(u.role, "value") else str(u.role),
            is_active=u.is_active,
            can_be_fee_earner=user_may_be_fee_earner(u, db),
            has_charge_rate=user_has_charge_rate(u),
        )
        for u in users
    ]


@router.get("/me/ledger-permissions", response_model=LedgerPermissionsOut)
def my_ledger_permissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> LedgerPermissionsOut:
    return LedgerPermissionsOut(
        can_approve_ledger=user_may_approve_ledger(user, db),
        can_approve_invoices=user_may_approve_invoice(user, db),
        accounts_workspace_access=user_may_access_accounts_workspace(user, db),
    )


@router.get("/me/calendar", response_model=UserCalDAVStatusOut)
def get_my_calendar(user: User = Depends(get_current_user)) -> UserCalDAVStatusOut:
    enabled = bool(user.caldav_password_enc)
    return UserCalDAVStatusOut(
        enabled=enabled,
        caldav_url=_caldav_principal_url(user.id),
        caldav_username=_caldav_username(user),
    )


@router.post("/me/calendar/enable", response_model=UserCalDAVProvisionOut)
def enable_my_calendar(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserCalDAVProvisionOut:
    if user.caldav_password_enc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CalDAV is already enabled. Use reset-password to rotate the app password, or disable first.",
        )
    plain = secrets.token_urlsafe(24)
    try:
        upsert_user(username=_caldav_username(user), plaintext_password=plain)
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not write CalDAV credentials: {e}",
        ) from e
    now = datetime.now(timezone.utc)
    user.caldav_password_enc = encrypt_password(plain)
    user.updated_at = now
    db.add(user)
    db.commit()
    ensure_default_calendar(db, user)
    return UserCalDAVProvisionOut(
        caldav_url=_caldav_principal_url(user.id),
        caldav_username=_caldav_username(user),
        caldav_password=plain,
    )


@router.post("/me/calendar/reset-password", response_model=UserCalDAVProvisionOut)
def reset_my_caldav_password(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserCalDAVProvisionOut:
    if not user.caldav_password_enc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CalDAV is not enabled")
    plain = secrets.token_urlsafe(24)
    try:
        upsert_user(username=_caldav_username(user), plaintext_password=plain)
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not write CalDAV credentials: {e}",
        ) from e
    now = datetime.now(timezone.utc)
    user.caldav_password_enc = encrypt_password(plain)
    user.updated_at = now
    db.add(user)
    db.commit()
    return UserCalDAVProvisionOut(
        caldav_url=_caldav_principal_url(user.id),
        caldav_username=_caldav_username(user),
        caldav_password=plain,
    )


@router.delete("/me/calendar/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_my_calendar(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    if not user.caldav_password_enc:
        return None
    remove_user(_caldav_username(user))
    user.caldav_password_enc = None
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return None


@router.put("/me/email-handling", response_model=UserPublic)
def put_my_email_handling(
    body: UserEmailHandlingUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    """Persist how matter e-mail compose opens (desktop mailto vs Outlook web)."""
    now = datetime.now(timezone.utc)
    user.email_launch_preference = body.email_launch_preference
    if body.email_launch_preference == "outlook_web":
        raw = (body.email_outlook_web_url or "").strip() or DEFAULT_OUTLOOK_MAIL_URL
        user.email_outlook_web_url = _validate_http_url(raw)
    else:
        user.email_outlook_web_url = None
    user.updated_at = now
    db.add(user)
    db.commit()
    db.refresh(user)
    return build_user_public(user, db)


@router.put("/me/appearance", response_model=UserPublic)
def put_my_appearance(
    body: UserAppearanceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    """Persist UI appearance preferences for this user account."""
    try:
        font, accent, mode, page_bg = normalize_appearance_update(
            font=body.font,
            accent=body.accent,
            mode=body.mode,
            page_bg=body.page_bg,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    user.appearance_font = font
    user.appearance_accent = accent
    user.appearance_mode = mode
    user.appearance_page_bg = page_bg
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return build_user_public(user, db)


@router.put("/me/ui-preferences", response_model=UserPublic)
def put_my_ui_preferences(
    body: UserUiPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPublic:
    """Persist UI layout preferences for this user account (calendar view, task layout, sort order)."""
    patch = UserUiPreferencesPatch.model_validate(body.model_dump(exclude_unset=True))
    user.ui_preferences = merge_ui_preferences_patch(user.ui_preferences, patch)
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return build_user_public(user, db)
