"""Rate limits for staff login and password-reset requests (Postgres-backed)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthRateLimitEntry

SCOPE_STAFF_LOGIN_EMAIL = "staff_login_email"
SCOPE_STAFF_LOGIN_IP = "staff_login_ip"
SCOPE_FORGOT_PASSWORD_EMAIL = "forgot_password_email"
SCOPE_FORGOT_PASSWORD_IP = "forgot_password_ip"
SCOPE_PORTAL_AUTH_IP = "portal_auth_ip"
SCOPE_PORTAL_OTP_REQUEST_EMAIL = "portal_otp_request_email"
SCOPE_PORTAL_OTP_REQUEST_IP = "portal_otp_request_ip"
SCOPE_PORTAL_OTP_VERIFY_EMAIL = "portal_otp_verify_email"
SCOPE_PORTAL_OTP_VERIFY_IP = "portal_otp_verify_ip"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def staff_login_max_attempts() -> int:
    return _int_env("STAFF_LOGIN_MAX_FAILED_ATTEMPTS", 5)


def staff_login_lockout_minutes() -> int:
    return _int_env("STAFF_LOGIN_LOCKOUT_MINUTES", 15)


def staff_login_ip_max_attempts() -> int:
    return _int_env("STAFF_LOGIN_IP_MAX_FAILED_ATTEMPTS", 25)


def forgot_password_max_attempts() -> int:
    return _int_env("FORGOT_PASSWORD_MAX_ATTEMPTS", 5)


def forgot_password_lockout_minutes() -> int:
    return _int_env("FORGOT_PASSWORD_LOCKOUT_MINUTES", 15)


def forgot_password_ip_max_attempts() -> int:
    return _int_env("FORGOT_PASSWORD_IP_MAX_ATTEMPTS", 15)


def portal_auth_ip_max_attempts() -> int:
    return _int_env("PORTAL_AUTH_IP_MAX_FAILED_ATTEMPTS", 25)


def portal_auth_lockout_minutes() -> int:
    return _int_env("PORTAL_AUTH_LOCKOUT_MINUTES", 15)


def portal_otp_request_email_max_attempts() -> int:
    return _int_env("PORTAL_OTP_REQUEST_EMAIL_MAX_ATTEMPTS", 5)


def portal_otp_request_ip_max_attempts() -> int:
    return _int_env("PORTAL_OTP_REQUEST_IP_MAX_ATTEMPTS", 15)


def portal_otp_request_lockout_minutes() -> int:
    return _int_env("PORTAL_OTP_REQUEST_LOCKOUT_MINUTES", 15)


def portal_otp_verify_email_max_attempts() -> int:
    return _int_env("PORTAL_OTP_VERIFY_EMAIL_MAX_FAILED_ATTEMPTS", 5)


def portal_otp_verify_ip_max_attempts() -> int:
    return _int_env("PORTAL_OTP_VERIFY_IP_MAX_FAILED_ATTEMPTS", 25)


def portal_otp_verify_lockout_minutes() -> int:
    return _int_env("PORTAL_OTP_VERIFY_LOCKOUT_MINUTES", 15)


def _normalize_identifier(raw: str) -> str:
    return (raw or "").strip().lower()[:320]


def _get_row(db: Session, *, scope: str, identifier: str) -> AuthRateLimitEntry | None:
    ident = _normalize_identifier(identifier)
    if not ident:
        return None
    return db.execute(
        select(AuthRateLimitEntry).where(
            AuthRateLimitEntry.scope == scope,
            AuthRateLimitEntry.identifier == ident,
        )
    ).scalar_one_or_none()


def _locked_until_active(row: AuthRateLimitEntry | None, *, now: datetime | None = None) -> datetime | None:
    if row is None or row.locked_until is None:
        return None
    now = now or utcnow()
    locked = row.locked_until
    if locked.tzinfo is None:
        locked = locked.replace(tzinfo=timezone.utc)
    if now < locked:
        return locked
    return None


def _lockout_message(*, locked_until: datetime, action: str) -> str:
    now = utcnow()
    remaining = locked_until - now
    minutes = max(1, int(remaining.total_seconds() + 59) // 60)
    return (
        f"Too many {action} attempts. "
        f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}."
    )


def assert_not_rate_limited(
    db: Session,
    *,
    scope: str,
    identifier: str | None,
    action: str,
) -> None:
    if not identifier:
        return
    row = _get_row(db, scope=scope, identifier=identifier)
    locked = _locked_until_active(row)
    if locked is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_lockout_message(locked_until=locked, action=action),
        )


def record_rate_limit_failure(
    db: Session,
    *,
    scope: str,
    identifier: str | None,
    max_attempts: int,
    lockout_minutes: int,
) -> None:
    if not identifier:
        return
    ident = _normalize_identifier(identifier)
    if not ident:
        return
    now = utcnow()
    row = _get_row(db, scope=scope, identifier=ident)
    if row is None:
        row = AuthRateLimitEntry(
            id=uuid.uuid4(),
            scope=scope,
            identifier=ident,
            failed_attempts=0,
            locked_until=None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    active_lock = _locked_until_active(row, now=now)
    if active_lock is not None:
        return
    row.failed_attempts = int(row.failed_attempts or 0) + 1
    if row.failed_attempts >= max_attempts:
        row.locked_until = now + timedelta(minutes=lockout_minutes)
        row.failed_attempts = 0
    row.updated_at = now
    db.add(row)
    db.commit()


def clear_rate_limit(db: Session, *, scope: str, identifier: str | None) -> None:
    if not identifier:
        return
    row = _get_row(db, scope=scope, identifier=identifier)
    if row is None:
        return
    row.failed_attempts = 0
    row.locked_until = None
    row.updated_at = utcnow()
    db.add(row)
    db.commit()


def check_staff_login_rate_limits(db: Session, *, email: str, ip: str | None) -> None:
    assert_not_rate_limited(db, scope=SCOPE_STAFF_LOGIN_EMAIL, identifier=email, action="sign-in")
    assert_not_rate_limited(db, scope=SCOPE_STAFF_LOGIN_IP, identifier=ip, action="sign-in")


def record_staff_login_failure(db: Session, *, email: str, ip: str | None) -> None:
    record_rate_limit_failure(
        db,
        scope=SCOPE_STAFF_LOGIN_EMAIL,
        identifier=email,
        max_attempts=staff_login_max_attempts(),
        lockout_minutes=staff_login_lockout_minutes(),
    )
    record_rate_limit_failure(
        db,
        scope=SCOPE_STAFF_LOGIN_IP,
        identifier=ip,
        max_attempts=staff_login_ip_max_attempts(),
        lockout_minutes=staff_login_lockout_minutes(),
    )


def clear_staff_login_rate_limits(db: Session, *, email: str) -> None:
    clear_rate_limit(db, scope=SCOPE_STAFF_LOGIN_EMAIL, identifier=email)


def check_forgot_password_rate_limits(db: Session, *, email: str, ip: str | None) -> None:
    assert_not_rate_limited(db, scope=SCOPE_FORGOT_PASSWORD_EMAIL, identifier=email, action="password reset")
    assert_not_rate_limited(db, scope=SCOPE_FORGOT_PASSWORD_IP, identifier=ip, action="password reset")


def record_forgot_password_attempt(db: Session, *, email: str, ip: str | None) -> None:
    record_rate_limit_failure(
        db,
        scope=SCOPE_FORGOT_PASSWORD_EMAIL,
        identifier=email,
        max_attempts=forgot_password_max_attempts(),
        lockout_minutes=forgot_password_lockout_minutes(),
    )
    record_rate_limit_failure(
        db,
        scope=SCOPE_FORGOT_PASSWORD_IP,
        identifier=ip,
        max_attempts=forgot_password_ip_max_attempts(),
        lockout_minutes=forgot_password_lockout_minutes(),
    )


def check_portal_auth_rate_limits(db: Session, *, ip: str | None) -> None:
    assert_not_rate_limited(db, scope=SCOPE_PORTAL_AUTH_IP, identifier=ip, action="portal sign-in")


def record_portal_auth_ip_failure(db: Session, *, ip: str | None) -> None:
    record_rate_limit_failure(
        db,
        scope=SCOPE_PORTAL_AUTH_IP,
        identifier=ip,
        max_attempts=portal_auth_ip_max_attempts(),
        lockout_minutes=portal_auth_lockout_minutes(),
    )


def check_portal_otp_request_rate_limits(db: Session, *, email: str, ip: str | None) -> None:
    assert_not_rate_limited(db, scope=SCOPE_PORTAL_OTP_REQUEST_EMAIL, identifier=email, action="sign-in code request")
    assert_not_rate_limited(db, scope=SCOPE_PORTAL_OTP_REQUEST_IP, identifier=ip, action="sign-in code request")


def record_portal_otp_request_attempt(db: Session, *, email: str, ip: str | None) -> None:
    record_rate_limit_failure(
        db,
        scope=SCOPE_PORTAL_OTP_REQUEST_EMAIL,
        identifier=email,
        max_attempts=portal_otp_request_email_max_attempts(),
        lockout_minutes=portal_otp_request_lockout_minutes(),
    )
    record_rate_limit_failure(
        db,
        scope=SCOPE_PORTAL_OTP_REQUEST_IP,
        identifier=ip,
        max_attempts=portal_otp_request_ip_max_attempts(),
        lockout_minutes=portal_otp_request_lockout_minutes(),
    )


def check_portal_otp_verify_rate_limits(db: Session, *, email: str, ip: str | None) -> None:
    assert_not_rate_limited(db, scope=SCOPE_PORTAL_OTP_VERIFY_EMAIL, identifier=email, action="sign-in code verification")
    assert_not_rate_limited(db, scope=SCOPE_PORTAL_OTP_VERIFY_IP, identifier=ip, action="sign-in code verification")


def record_portal_otp_verify_failure(db: Session, *, email: str, ip: str | None) -> None:
    record_rate_limit_failure(
        db,
        scope=SCOPE_PORTAL_OTP_VERIFY_EMAIL,
        identifier=email,
        max_attempts=portal_otp_verify_email_max_attempts(),
        lockout_minutes=portal_otp_verify_lockout_minutes(),
    )
    record_rate_limit_failure(
        db,
        scope=SCOPE_PORTAL_OTP_VERIFY_IP,
        identifier=ip,
        max_attempts=portal_otp_verify_ip_max_attempts(),
        lockout_minutes=portal_otp_verify_lockout_minutes(),
    )


def clear_portal_otp_verify_rate_limits(db: Session, *, email: str) -> None:
    clear_rate_limit(db, scope=SCOPE_PORTAL_OTP_VERIFY_EMAIL, identifier=email)
