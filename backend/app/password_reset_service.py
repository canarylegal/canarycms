"""Staff and self-service password reset e-mail plus password rotation policy."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.alert_templates import password_reset_email
from app.audit import log_event
from app.canary_public_url import canary_public_url
from app.firm_email_service import FirmEmailMessage, resolve_alert_transport, try_send_firm_email
from app.models import FirmSettings, PasswordResetToken, User
from app.org_security import user_password_change_required

PASSWORD_RESET_TTL = timedelta(hours=1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def password_reset_email_configured(db: Session) -> bool:
    return resolve_alert_transport(db) is not None


def _hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _purge_expired_tokens(db: Session) -> None:
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < utcnow()))


def _reset_link(raw_token: str) -> str:
    base = canary_public_url().rstrip("/")
    return f"{base}/?reset_token={raw_token}"


def create_password_reset_token(db: Session, user: User) -> str:
    """Invalidate prior tokens and return a new single-use reset token (plaintext)."""
    _purge_expired_tokens(db)
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    raw = secrets.token_urlsafe(32)
    row = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_sha256=_hash_reset_token(raw),
        expires_at=utcnow() + PASSWORD_RESET_TTL,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return raw


def consume_password_reset_token(db: Session, raw_token: str) -> User | None:
    digest = _hash_reset_token((raw_token or "").strip())
    now = utcnow()
    row = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_sha256 == digest,
            PasswordResetToken.expires_at >= now,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.flush()
    return user


def send_password_reset_email(
    db: Session,
    user: User,
    raw_token: str,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    addr = (user.email or "").strip()
    if not addr:
        return False
    if not password_reset_email_configured(db):
        return False
    firm = db.get(FirmSettings, 1)
    firm_name = ""
    if firm:
        firm_name = (firm.trading_name or "").strip() or (firm.registered_company_name or "").strip()
    subject, body = password_reset_email(
        firm_name=firm_name,
        display_name=user.display_name,
        reset_url=_reset_link(raw_token),
    )
    transport = try_send_firm_email(db, FirmEmailMessage(to_email=addr, subject=subject, body_text=body))
    if transport is None:
        return False
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="auth.password.reset_email",
        entity_type="user",
        entity_id=str(user.id),
        meta={"email": addr, "transport": transport},
    )
    db.commit()
    return True


def touch_password_changed(user: User, *, when: datetime | None = None) -> None:
    user.password_changed_at = when or utcnow()
    user.updated_at = when or utcnow()


def login_access_token(db: Session, user: User, *, mfa_verified: bool) -> str:
    from app.security import create_access_token

    password_ok = not user_password_change_required(db, user)
    return create_access_token(
        user_id=str(user.id),
        role=user.role.value,
        mfa_verified=mfa_verified,
        password_ok=password_ok,
        auth_token_version=int(user.auth_token_version),
    )
