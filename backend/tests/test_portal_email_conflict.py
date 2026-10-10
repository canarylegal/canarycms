"""Same-email portal login conflict detection and resolution."""

from __future__ import annotations

import uuid
from datetime import datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditEvent, Base, Case, Contact, ContactPortalAccess, ContactPortalGrant, ContactType, User
from app.portal_email_conflict import (
    PORTAL_EMAIL_CONFLICT_CODE,
    disable_portal_access_for_conflict,
    find_active_portal_email_conflict,
    join_existing_portal_login,
    require_no_unresolved_portal_email_conflict,
)
from app.portal_service import portal_access_is_active, store_portal_access_code


CODE_A = "AAAA1111BBBB"


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
            ContactPortalGrant.__table__,
            AuditEvent.__table__,
        ):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _user(db: Session) -> User:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"fee-{uid.hex[:6]}@example.com",
        password_hash="x",
        display_name="Fee Earner",
        initials="FE",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    return user


def _contact(db: Session, *, email: str, name: str = "Alex") -> Contact:
    c = Contact(
        id=uuid.uuid4(),
        type=ContactType.person,
        name=name,
        email=email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(c)
    db.commit()
    return c


def _enable_access(db: Session, contact: Contact, user: User, code: str) -> ContactPortalAccess:
    row = ContactPortalAccess(
        id=uuid.uuid4(),
        contact_id=contact.id,
        enabled=True,
        created_by_user_id=user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    store_portal_access_code(row, code)
    db.add(row)
    db.commit()
    return row


def test_no_conflict_when_email_empty() -> None:
    db = _session()
    user = _user(db)
    a = _contact(db, email="")
    _enable_access(db, a, user, CODE_A)
    b = _contact(db, email="")
    assert find_active_portal_email_conflict(db, contact_id=b.id) is None


def test_no_conflict_when_other_disabled() -> None:
    db = _session()
    user = _user(db)
    a = _contact(db, email="same@example.com", name="Earlier")
    row = _enable_access(db, a, user, CODE_A)
    row.enabled = False
    db.add(row)
    db.commit()
    b = _contact(db, email="same@example.com", name="Later")
    assert find_active_portal_email_conflict(db, contact_id=b.id) is None


def test_conflict_case_insensitive() -> None:
    db = _session()
    user = _user(db)
    a = _contact(db, email="Same@Example.com", name="Earlier")
    _enable_access(db, a, user, CODE_A)
    b = _contact(db, email="same@example.com", name="Later")
    conflict = find_active_portal_email_conflict(db, contact_id=b.id)
    assert conflict is not None
    assert conflict.other_contact.id == a.id
    assert conflict.email == "same@example.com"


def test_require_unresolved_raises_structured_409() -> None:
    db = _session()
    user = _user(db)
    a = _contact(db, email="dup@example.com", name="Earlier")
    _enable_access(db, a, user, CODE_A)
    b = _contact(db, email="dup@example.com", name="Later")
    with pytest.raises(HTTPException) as ei:
        require_no_unresolved_portal_email_conflict(db, contact_id=b.id, conflict_resolution=None)
    assert ei.value.status_code == 409
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == PORTAL_EMAIL_CONFLICT_CODE
    assert detail["other_contact_id"] == str(a.id)


def test_revoke_other_disables_earlier_login(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    user = _user(db)
    a = _contact(db, email="dup@example.com", name="Earlier")
    row_a = _enable_access(db, a, user, CODE_A)
    b = _contact(db, email="dup@example.com", name="Later")
    monkeypatch.setattr("app.portal_email_conflict.log_event", lambda *a, **k: None)
    disable_portal_access_for_conflict(
        db,
        other_contact_id=a.id,
        actor_user_id=user.id,
        superseded_by_contact_id=b.id,
    )
    db.commit()
    db.refresh(row_a)
    assert not portal_access_is_active(row_a)
    assert row_a.code_enc is None
    assert find_active_portal_email_conflict(db, contact_id=b.id) is None


def test_join_existing_keeps_other_code(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _session()
    user = _user(db)
    a = _contact(db, email="dup@example.com", name="Earlier")
    row_a = _enable_access(db, a, user, CODE_A)
    b = _contact(db, email="dup@example.com", name="Later")
    monkeypatch.setattr("app.portal_email_conflict.log_event", lambda *a, **k: None)
    conflict = find_active_portal_email_conflict(db, contact_id=b.id)
    assert conflict is not None
    code, relinked = join_existing_portal_login(
        db,
        contact_id=b.id,
        conflict=conflict,
        case_id=None,
        actor_user_id=user.id,
    )
    db.commit()
    assert code.replace("-", "") == CODE_A.replace("-", "")
    assert relinked is False
    db.refresh(row_a)
    assert portal_access_is_active(row_a)
    assert find_active_portal_email_conflict(db, contact_id=b.id) is not None
