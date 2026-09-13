"""Shared checkout for WebDAV desktop edit and ONLYOFFICE browser editor."""

from __future__ import annotations

import os
import secrets
import uuid
import zlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import File as DbFile, FileCategory, FileEditSession, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def webdav_session_hours() -> int:
    try:
        return max(1, min(72, int(os.getenv("WEBDAV_SESSION_HOURS", "8"))))
    except ValueError:
        return 8


def _locked_by_name(db: Session, sess: FileEditSession) -> str:
    other = db.get(User, sess.user_id)
    return (other.display_name if other else None) or "Another user"


def active_edit_sessions_for_files(db: Session, file_ids: list[uuid.UUID]) -> list[FileEditSession]:
    if not file_ids:
        return []
    now = _utcnow()
    return list(
        db.execute(
            select(FileEditSession).where(
                FileEditSession.file_id.in_(file_ids),
                FileEditSession.released_at.is_(None),
                FileEditSession.expires_at > now,
            )
        )
        .scalars()
        .all()
    )


def raise_if_files_checked_out(db: Session, file_ids: list[uuid.UUID], *, action: str = "change") -> None:
    """Reject rename/move/delete when any of the files has an active desktop/OO edit session (CL-06)."""
    active = active_edit_sessions_for_files(db, file_ids)
    if not active:
        return
    locked_name = _locked_by_name(db, active[0])
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": (
                f"This file is checked out for editing by {locked_name}. "
                f"Stop desktop or browser editing before you {action} it."
            ),
            "locked_by": locked_name,
        },
    )


def release_edit_sessions_for_user(
    db: Session,
    user_id: uuid.UUID,
    *,
    case_id: uuid.UUID | None = None,
) -> int:
    """Mark open edit sessions released (account disable / matter deny). Returns count released."""
    now = _utcnow()
    q = select(FileEditSession).where(
        FileEditSession.user_id == user_id,
        FileEditSession.released_at.is_(None),
        FileEditSession.expires_at > now,
    )
    if case_id is not None:
        q = q.where(FileEditSession.case_id == case_id)
    rows = list(db.execute(q).scalars().all())
    for sess in rows:
        sess.released_at = now
        db.add(sess)
    return len(rows)


def session_owner_still_authorized(db: Session, sess: FileEditSession) -> User | None:
    """Return the session owner if they may still edit; otherwise None (CL-07)."""
    from app.deps import get_case_if_accessible

    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        return None
    if sess.case_id is not None and get_case_if_accessible(sess.case_id, user, db) is None:
        return None
    return user


def acquire_file_edit_session(
    db: Session,
    *,
    case_id: uuid.UUID | None,
    file_id: uuid.UUID,
    user: User,
) -> tuple[FileEditSession, DbFile]:
    """
    Return a WebDAV-capable edit session for this user and file.

    If the same user already has exactly one active session for this file, it is returned as-is (avoids
    invalidating a ONLYOFFICE JWT when the client double-calls acquire). Otherwise any prior sessions for
    this user on the file are released and a new session is created.

    Raises 409 if another user holds an active session.
    """
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.category == FileCategory.system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit folder markers via WebDAV",
        )

    # Serialize checkout per file so two concurrent onlyoffice-config calls (e.g. React Strict Mode)
    # cannot both insert an active FileEditSession. That leaves two rows for the same user+file; the
    # next acquire hits len(mine) > 1, releases *all* (including the token already embedded in a JWT
    # ONLYOFFICE is fetching) → WebDAV 404 → ONLYOFFICE error -4 "Download failed."
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        lock_k2 = zlib.crc32(file_id.bytes) & 0x7FFFFFFF
        db.execute(text("SELECT pg_advisory_xact_lock(582013711, :k2)"), {"k2": lock_k2})

    now = _utcnow()
    active = (
        db.execute(
            select(FileEditSession).where(
                FileEditSession.file_id == file_id,
                FileEditSession.released_at.is_(None),
                FileEditSession.expires_at > now,
            )
        )
        .scalars()
        .all()
    )
    others = [s for s in active if s.user_id != user.id]
    if others:
        locked_name = _locked_by_name(db, others[0])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"This file is already being edited by {locked_name}.",
                "locked_by": locked_name,
            },
        )

    mine = [s for s in active if s.user_id == user.id]
    # Re-use the existing WebDAV session when the same user hits acquire again immediately (e.g. React
    # StrictMode / duplicate onlyoffice-config). Releasing the prior session here invalidates document.url
    # in a JWT that ONLYOFFICE has not fetched yet → blank editor and no GET /webdav in backend logs.
    if len(mine) == 1:
        sess = mine[0]
        db.refresh(sess)
        return sess, row

    for s in mine:
        s.released_at = now
        db.add(s)

    hours = webdav_session_hours()
    expires = now + timedelta(hours=hours)
    token = secrets.token_urlsafe(48)
    sess = FileEditSession(
        id=uuid.uuid4(),
        token=token,
        file_id=file_id,
        case_id=case_id,
        user_id=user.id,
        created_at=now,
        expires_at=expires,
        released_at=None,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess, row
