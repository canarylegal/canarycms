"""Desktop edit session auth and checkout conflict helpers (CL-06 / CL-07)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.desktop_edit_session import (
    raise_if_files_checked_out,
    release_edit_sessions_for_user,
    session_owner_still_authorized,
)
from app.models import Base, Case, CaseAccessRule, CaseLockMode, CaseStatus, FileEditSession, User


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (User.__table__, Case.__table__, CaseAccessRule.__table__, FileEditSession.__table__):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _user(db: Session, *, active: bool = True) -> User:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    user = User(
        id=uid,
        email=f"u-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name="Editor",
        initials="ED",
        is_active=active,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _case(db: Session, fee: User) -> Case:
    now = datetime.now(timezone.utc)
    case = Case(
        id=uuid.uuid4(),
        case_number="000777",
        title="Edit session matter",
        fee_earner_user_id=fee.id,
        created_by=fee.id,
        status=CaseStatus.open,
        lock_mode=CaseLockMode.none,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _sess(db: Session, *, user: User, case: Case, file_id: uuid.UUID) -> FileEditSession:
    now = datetime.now(timezone.utc)
    row = FileEditSession(
        id=uuid.uuid4(),
        token="tok-" + uuid.uuid4().hex,
        file_id=file_id,
        case_id=case.id,
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(hours=2),
        released_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_raise_if_files_checked_out_conflicts() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    fid = uuid.uuid4()
    _sess(db, user=user, case=case, file_id=fid)
    try:
        raise_if_files_checked_out(db, [fid], action="rename")
        raise AssertionError("expected 409")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "checked out" in str(exc.detail).lower() or (
            isinstance(exc.detail, dict) and "checked out" in exc.detail["message"].lower()
        )


def test_inactive_owner_not_authorized() -> None:
    db = _session()
    user = _user(db, active=True)
    case = _case(db, user)
    fid = uuid.uuid4()
    sess = _sess(db, user=user, case=case, file_id=fid)
    assert session_owner_still_authorized(db, sess) is not None
    user.is_active = False
    db.add(user)
    db.commit()
    assert session_owner_still_authorized(db, sess) is None


def test_release_edit_sessions_for_user() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    fid = uuid.uuid4()
    sess = _sess(db, user=user, case=case, file_id=fid)
    n = release_edit_sessions_for_user(db, user.id, case_id=case.id)
    db.commit()
    db.refresh(sess)
    assert n == 1
    assert sess.released_at is not None
    raise_if_files_checked_out(db, [fid])  # no longer active
