"""Organisation-wide security policy helpers (2FA mandate, passkeys, password rotation)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FirmSettings, User, WebAuthnCredential


def firm_mandates_second_factor(db: Session) -> bool:
    row = db.get(FirmSettings, 1)
    return bool(row and row.mandate_two_factor)


def firm_password_rotation_policy(db: Session) -> tuple[bool, int | None]:
    row = db.get(FirmSettings, 1)
    if not row or not row.mandate_password_rotation:
        return False, None
    days = row.password_rotation_days
    if days is None or days < 1:
        return True, None
    return True, int(days)


def user_password_change_required(db: Session, user: User) -> bool:
    enabled, days = firm_password_rotation_policy(db)
    if not enabled or days is None:
        return False
    changed = user.password_changed_at or user.created_at
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - changed
    return age >= timedelta(days=days)


def user_has_any_passkey(db: Session, user_id: uuid.UUID) -> bool:
    q = select(WebAuthnCredential.id).where(WebAuthnCredential.user_id == user_id).limit(1)
    return db.execute(q).scalar_one_or_none() is not None


def user_meets_second_factor_policy(db: Session, user_id: uuid.UUID, *, is_2fa_enabled: bool) -> bool:
    """Satisfied when TOTP is enabled or the user has registered at least one passkey."""

    if is_2fa_enabled:
        return True
    return user_has_any_passkey(db, user_id)
