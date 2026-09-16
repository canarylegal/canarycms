"""Portal auth service: access-code and OTP request/verify flows."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditEvent,
    Base,
    Case,
    Contact,
    ContactPortalAccess,
    ContactType,
    MatterPortalAccess,
    PortalLoginOtp,
    User,
)
from app.portal_auth_service import portal_auth, portal_request_otp, portal_verify_otp
from app.portal_service import hash_access_code, issue_portal_login_otp
from app.schemas import PortalAuthIn, PortalOtpRequestIn, PortalOtpVerifyIn


ACCESS_CODE = "ABCD1234WXYZ"


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (
            User.__table__,
            Case.__table__,
            Contact.__table__,
            ContactPortalAccess.__table__,
            MatterPortalAccess.__table__,
            PortalLoginOtp.__table__,
            AuditEvent.__table__,
        ):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _request(ip: str = "203.0.113.50") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    return req


def _seed_contact(db: Session, *, email: str = "client@example.com", enabled: bool = True) -> Contact:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"fee-{uid.hex[:6]}@example.com",
        password_hash="x",
        display_name="Fee Earner",
        initials=f"F{uid.hex[:3].upper()}",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    contact = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name="Alex Client",
        email=email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add_all([user, contact])
    db.add(
        ContactPortalAccess(
            id=uuid.uuid4(),
            contact_id=contact.id,
            code_sha256=hash_access_code(ACCESS_CODE),
            enabled=enabled,
            created_by_user_id=user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    return contact


def _patch_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "check_portal_auth_rate_limits",
        "check_portal_otp_request_rate_limits",
        "check_portal_otp_verify_rate_limits",
        "record_portal_auth_ip_failure",
        "record_portal_otp_request_attempt",
        "record_portal_otp_verify_failure",
        "clear_portal_otp_verify_rate_limits",
    ):
        monkeypatch.setattr(f"app.portal_auth_service.{name}", lambda *a, **k: None)
    monkeypatch.setattr("app.portal_auth_service.grant_summaries", lambda *a, **k: [])
    monkeypatch.setattr("app.portal_auth_service.portal_public_url", lambda: "https://portal.test")


def test_portal_auth_success(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    contact = _seed_contact(db)
    _patch_rate_limits(monkeypatch)
    out = portal_auth(PortalAuthIn(access_code=ACCESS_CODE), _request(), db)
    assert out.contact_name == "Alex Client"
    assert out.audience == "client"
    assert out.session_token
    assert out.staff_preview is False


def test_portal_auth_rejects_invalid_code(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    _seed_contact(db)
    _patch_rate_limits(monkeypatch)
    with pytest.raises(HTTPException) as ei:
        portal_auth(PortalAuthIn(access_code="ZZZZ9999AAAA"), _request(), db)
    assert ei.value.status_code == 401


def test_portal_auth_rejects_disabled_access(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    _seed_contact(db, enabled=False)
    _patch_rate_limits(monkeypatch)
    with pytest.raises(HTTPException) as ei:
        portal_auth(PortalAuthIn(access_code=ACCESS_CODE), _request(), db)
    assert ei.value.status_code == 401


def test_portal_request_otp_dispatches_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    contact = _seed_contact(db, email="otp@example.com")
    _patch_rate_limits(monkeypatch)
    captured: list[dict] = []

    def _capture(db_arg, kind, *, to_email, context):
        captured.append({"kind": kind, "to_email": to_email, "context": context})

    monkeypatch.setattr("app.portal_auth_service.dispatch_alert", _capture)
    portal_request_otp(PortalOtpRequestIn(email="otp@example.com"), _request(), db)
    assert len(captured) == 1
    assert captured[0]["to_email"] == contact.email
    assert len(captured[0]["context"]["otp_code"]) == 6


def test_portal_request_otp_silent_for_unknown_email(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    _seed_contact(db)
    _patch_rate_limits(monkeypatch)
    called = {"n": 0}

    def _capture(*a, **k):
        called["n"] += 1

    monkeypatch.setattr("app.portal_auth_service.dispatch_alert", _capture)
    portal_request_otp(PortalOtpRequestIn(email="unknown@example.com"), _request(), db)
    assert called["n"] == 0


def test_portal_verify_otp_success(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    contact = _seed_contact(db, email="verify@example.com")
    _patch_rate_limits(monkeypatch)
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    out = portal_verify_otp(
        PortalOtpVerifyIn(email="verify@example.com", code=code),
        _request(),
        db,
    )
    assert out.contact_name == "Alex Client"
    assert out.session_token
    assert out.audience == "client"


def test_portal_verify_otp_rejects_bad_code(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    contact = _seed_contact(db, email="verify@example.com")
    _patch_rate_limits(monkeypatch)
    issue_portal_login_otp(db, contact.id)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        portal_verify_otp(
            PortalOtpVerifyIn(email="verify@example.com", code="999999"),
            _request(),
            db,
        )
    assert ei.value.status_code == 401
