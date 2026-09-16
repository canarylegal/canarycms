"""Portal login OTP issue/verify and e-mail contact lookup."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Base,
    Case,
    Contact,
    ContactPortalAccess,
    ContactType,
    PortalLoginOtp,
    User,
)
from app.portal_service import (
    find_portal_contact_by_email,
    hash_access_code,
    issue_portal_login_otp,
    verify_portal_login_otp,
)


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
            PortalLoginOtp.__table__,
        ):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _seed_contact(db: Session, *, email: str = "client@example.com", enabled: bool = True) -> tuple[User, Contact]:
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
            code_sha256=hash_access_code("ABCD1234WXYZ"),
            enabled=enabled,
            created_by_user_id=user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    return user, contact


def test_issue_portal_login_otp_returns_six_digit_code() -> None:
    db = _session()
    _, contact = _seed_contact(db)
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    assert len(code) == 6
    assert code.isdigit()
    rows = db.execute(select(PortalLoginOtp).where(PortalLoginOtp.contact_id == contact.id)).scalars().all()
    assert len(rows) == 1
    assert rows[0].used_at is None


def test_verify_portal_login_otp_success() -> None:
    db = _session()
    _, contact = _seed_contact(db)
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    assert verify_portal_login_otp(db, contact.id, code) is True
    db.commit()
    row = db.execute(select(PortalLoginOtp).where(PortalLoginOtp.contact_id == contact.id)).scalar_one()
    assert row.used_at is not None


def test_verify_portal_login_otp_rejects_wrong_code() -> None:
    db = _session()
    _, contact = _seed_contact(db)
    issue_portal_login_otp(db, contact.id)
    db.commit()
    assert verify_portal_login_otp(db, contact.id, "000000") is False


def test_verify_portal_login_otp_rejects_reuse() -> None:
    db = _session()
    _, contact = _seed_contact(db)
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    assert verify_portal_login_otp(db, contact.id, code) is True
    db.commit()
    assert verify_portal_login_otp(db, contact.id, code) is False


def test_issue_invalidates_prior_unused_codes() -> None:
    db = _session()
    _, contact = _seed_contact(db)
    first = issue_portal_login_otp(db, contact.id)
    db.commit()
    second = issue_portal_login_otp(db, contact.id)
    db.commit()
    assert verify_portal_login_otp(db, contact.id, first) is False
    assert verify_portal_login_otp(db, contact.id, second) is True


def test_verify_rejects_expired_otp() -> None:
    db = _session()
    _, contact = _seed_contact(db)
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    row = db.execute(select(PortalLoginOtp).where(PortalLoginOtp.contact_id == contact.id)).scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(row)
    db.commit()
    assert verify_portal_login_otp(db, contact.id, code) is False


def test_find_portal_contact_by_email_active() -> None:
    db = _session()
    _, contact = _seed_contact(db, email="Active.Client@Example.COM")
    found = find_portal_contact_by_email(db, "active.client@example.com")
    assert found is not None
    assert found.id == contact.id


def test_find_portal_contact_by_email_inactive() -> None:
    db = _session()
    _seed_contact(db, email="inactive@example.com", enabled=False)
    assert find_portal_contact_by_email(db, "inactive@example.com") is None


def test_find_portal_contact_by_email_unknown_or_blank() -> None:
    db = _session()
    _seed_contact(db)
    assert find_portal_contact_by_email(db, "nobody@example.com") is None
    assert find_portal_contact_by_email(db, "  ") is None
