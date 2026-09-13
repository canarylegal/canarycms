"""Staff logout invalidates JWTs via auth_token_version (pen-test session lifecycle)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

from app.models import AuditEvent, Base, User
from app.routers.auth import _invalidate_staff_jwt_on_logout
from app.security import create_access_token, create_master_recovery_token, decode_access_token


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (User.__table__, AuditEvent.__table__):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _user(db, *, tv: int = 1) -> User:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    user = User(
        id=uid,
        email=f"u-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name="Tester",
        initials="TE",
        auth_token_version=tv,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_logout_bumps_version_for_current_token() -> None:
    db = _session()
    user = _user(db, tv=3)
    token = create_access_token(
        user_id=str(user.id),
        role="user",
        auth_token_version=3,
    )
    _invalidate_staff_jwt_on_logout(db, token)
    db.refresh(user)
    assert user.auth_token_version == 4
    # Stale token must not bump again (would invalidate a fresh login).
    _invalidate_staff_jwt_on_logout(db, token)
    db.refresh(user)
    assert user.auth_token_version == 4


def test_logout_ignores_master_recovery_token() -> None:
    db = _session()
    user = _user(db, tv=1)
    before = user.auth_token_version
    _invalidate_staff_jwt_on_logout(db, create_master_recovery_token())
    db.refresh(user)
    assert user.auth_token_version == before


def test_logout_noop_without_token() -> None:
    db = _session()
    _invalidate_staff_jwt_on_logout(db, None)
    _invalidate_staff_jwt_on_logout(db, "not-a-jwt")


def test_decode_rejects_mismatched_tv_semantics() -> None:
    """Sanity: bumped version means old JWT payload tv no longer matches user row."""
    db = _session()
    user = _user(db, tv=1)
    token = create_access_token(user_id=str(user.id), role="user", auth_token_version=1)
    payload = decode_access_token(token)
    assert payload.auth_token_version == 1
    _invalidate_staff_jwt_on_logout(db, token)
    db.refresh(user)
    assert payload.auth_token_version != int(user.auth_token_version)
