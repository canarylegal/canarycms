"""Organisation-wide security policy helpers (2FA mandate, passkeys)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FirmSettings, WebAuthnCredential


def firm_mandates_second_factor(db: Session) -> bool:
    row = db.get(FirmSettings, 1)
    return bool(row and row.mandate_two_factor)


def user_has_any_passkey(db: Session, user_id: uuid.UUID) -> bool:
    q = select(WebAuthnCredential.id).where(WebAuthnCredential.user_id == user_id).limit(1)
    return db.execute(q).scalar_one_or_none() is not None


def user_meets_second_factor_policy(db: Session, user_id: uuid.UUID, *, is_2fa_enabled: bool) -> bool:
    """Satisfied when TOTP is enabled or the user has registered at least one passkey."""

    if is_2fa_enabled:
        return True
    return user_has_any_passkey(db, user_id)
