"""Unit tests for calendar access helpers and colour normalisation (SQLite)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.calendar_category import normalize_calendar_color
from app.calendar_service import (
    CalendarAccess,
    default_calendar_title,
    require_write,
    resolve_calendar_access,
)
from app.models import Base, User, UserCalendar, UserCalendarShare, UserCalendarSubscription


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    tables = (
        User.__table__,
        UserCalendar.__table__,
        UserCalendarShare.__table__,
        UserCalendarSubscription.__table__,
    )
    try:
        for table in tables:
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _user(db: Session, *, display_name: str = "Test User") -> User:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    row = User(
        id=uid,
        email=f"u-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name=display_name,
        initials=f"U{uid.hex[:3].upper()}",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _calendar(db: Session, owner: User, *, is_public: bool = False) -> UserCalendar:
    now = datetime.now(timezone.utc)
    row = UserCalendar(
        id=uuid.uuid4(),
        owner_user_id=owner.id,
        name="Work",
        radicale_slug=f"cal-{uuid.uuid4().hex[:8]}",
        is_public=is_public,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_default_calendar_title_possessive() -> None:
    alex = User(
        id=uuid.uuid4(),
        email="a@example.com",
        password_hash="x",
        display_name="Alex",
        initials="AL",
    )
    chris = User(
        id=uuid.uuid4(),
        email="c@example.com",
        password_hash="x",
        display_name="Chris",
        initials="CH",
    )
    assert default_calendar_title(alex) == "Alex's Calendar"
    assert default_calendar_title(chris) == "Chris' Calendar"


def test_normalize_calendar_color() -> None:
    assert normalize_calendar_color(None) is None
    assert normalize_calendar_color("  ") is None
    assert normalize_calendar_color("#aabbcc") == "#AABBCC"
    assert normalize_calendar_color("ff00aa") == "#FF00AA"
    with pytest.raises(HTTPException) as exc:
        normalize_calendar_color("#xyz")
    assert exc.value.status_code == 400


def test_resolve_calendar_access_owner() -> None:
    db = _session()
    owner = _user(db)
    cal = _calendar(db, owner)
    access = resolve_calendar_access(db, owner, cal.id)
    assert access.permission == "owner"
    assert access.dav_user.id == owner.id


def test_resolve_calendar_access_share_read_write() -> None:
    db = _session()
    owner = _user(db, display_name="Owner")
    grantee = _user(db, display_name="Grantee")
    cal = _calendar(db, owner)
    db.add(UserCalendarShare(calendar_id=cal.id, grantee_user_id=grantee.id, can_write=False))
    db.commit()
    access = resolve_calendar_access(db, grantee, cal.id)
    assert access.permission == "read"
    assert access.dav_user.id == owner.id

    share = db.get(UserCalendarShare, (cal.id, grantee.id))
    assert share is not None
    share.can_write = True
    db.add(share)
    db.commit()
    access_w = resolve_calendar_access(db, grantee, cal.id)
    assert access_w.permission == "write"


def test_resolve_calendar_access_forbidden() -> None:
    db = _session()
    owner = _user(db)
    stranger = _user(db, display_name="Stranger")
    cal = _calendar(db, owner)
    with pytest.raises(HTTPException) as exc:
        resolve_calendar_access(db, stranger, cal.id)
    assert exc.value.status_code == 403


def test_require_write() -> None:
    db = _session()
    owner = _user(db)
    cal = _calendar(db, owner)
    owner_access = CalendarAccess(cal, "owner", owner)
    require_write(owner_access)
    with pytest.raises(HTTPException) as exc:
        require_write(CalendarAccess(cal, "read", owner))
    assert exc.value.status_code == 403
