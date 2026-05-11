"""Singleton SMTP settings for outbound notification e-mail."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import SmtpNotificationSettings


def get_smtp_notification_settings(db: Session) -> SmtpNotificationSettings:
    row = db.get(SmtpNotificationSettings, 1)
    if row is None:
        row = SmtpNotificationSettings(id=1)
        db.add(row)
        db.flush()
    return row
