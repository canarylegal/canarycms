"""Tests for staff auth rate limiting."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth_rate_limit import (
    SCOPE_STAFF_LOGIN_EMAIL,
    assert_not_rate_limited,
    check_staff_login_rate_limits,
    clear_staff_login_rate_limits,
    record_rate_limit_failure,
    record_staff_login_failure,
)
from app.models import AuthRateLimitEntry


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AuthRateLimitEntry.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def test_locks_after_max_failures(db: Session) -> None:
    email = "user@example.com"
    for _ in range(4):
        record_rate_limit_failure(
            db,
            scope=SCOPE_STAFF_LOGIN_EMAIL,
            identifier=email,
            max_attempts=5,
            lockout_minutes=15,
        )
    assert_not_rate_limited(db, scope=SCOPE_STAFF_LOGIN_EMAIL, identifier=email, action="sign-in")
    record_rate_limit_failure(
        db,
        scope=SCOPE_STAFF_LOGIN_EMAIL,
        identifier=email,
        max_attempts=5,
        lockout_minutes=15,
    )
    with pytest.raises(HTTPException) as exc:
        assert_not_rate_limited(db, scope=SCOPE_STAFF_LOGIN_EMAIL, identifier=email, action="sign-in")
    assert exc.value.status_code == 429


def test_success_clears_email_counter(db: Session) -> None:
    email = "cleared@example.com"
    record_staff_login_failure(db, email=email, ip=None)
    clear_staff_login_rate_limits(db, email=email)
    assert_not_rate_limited(db, scope=SCOPE_STAFF_LOGIN_EMAIL, identifier=email, action="sign-in")


def test_check_staff_login_rate_limits_uses_ip(db: Session) -> None:
    ip = "203.0.113.10"
    locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.add(
        AuthRateLimitEntry(
            id=uuid.uuid4(),
            scope="staff_login_ip",
            identifier=ip,
            failed_attempts=0,
            locked_until=locked_until,
        )
    )
    db.commit()
    with pytest.raises(HTTPException) as exc:
        check_staff_login_rate_limits(db, email="anyone@example.com", ip=ip)
    assert exc.value.status_code == 429
