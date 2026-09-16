"""Case folder lock, settle, marker, and CRUD helpers (CL-05 / CL-09)."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.deps import require_case_access
from app.desktop_edit_session import raise_if_files_checked_out
from app.file_storage import case_file_paths, ensure_files_root, sanitize_folder_path
from app.models import File as DbFile, FileCategory, User
from app.schemas import CaseFolderCreate, CaseFolderDeleteUpdate, CaseFolderMoveUpdate, CaseFolderRenameUpdate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _folder_has_non_system_content(db: Session, case_id: uuid.UUID, folder_path: str) -> bool:
    prefix = folder_path
    like = f"{prefix}/%"
    row = db.execute(
        select(DbFile.id)
        .where(
            DbFile.case_id == case_id,
            DbFile.category != FileCategory.system,
            or_(DbFile.folder_path == prefix, DbFile.folder_path.like(like)),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


# Same lock namespace as folder rename (CL-05); try-lock used for upload vs delete (CL-09).
_FOLDER_OPS_LOCK_KEY1 = 582013712
_FOLDER_BUSY_DETAIL = "Another folder operation is in progress on this matter. Try again in a moment."
_FOLDER_GONE_DETAIL = "Destination folder was deleted or no longer exists."
_FOLDER_ALREADY_DELETED_DETAIL = "Folder was already deleted or no longer exists."
_FOLDER_MODIFIED_DURING_DELETE_DETAIL = (
    "Folder was modified during deletion (a concurrent upload finished first). Try again."
)
_FOLDER_UPLOAD_SETTLING_DETAIL = (
    "A recent upload to this folder is still settling. Try again in a moment."
)
_FILE_MOVE_CONFLICT_DETAIL = "File was deleted or moved by another user. Refresh and try again."
# Brief window after upload so a concurrent recursive delete conflicts instead of
# removing the object the uploader was just told exists (CL-09).
_UPLOAD_SETTLE_SECONDS = 5


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize DB timestamps for comparison (SQLite may return naive UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _db_now(db: Session) -> datetime:
    from sqlalchemy import func

    return _as_utc(db.execute(select(func.now())).scalar_one()) or _utcnow()


def _touch_folder_upload_settle(db: Session, case_id: uuid.UUID, folder_path: str) -> None:
    """Mark the folder marker protected until now+_UPLOAD_SETTLE_SECONDS (CL-09)."""
    if not folder_path:
        return
    marker = db.execute(
        select(DbFile)
        .where(
            DbFile.case_id == case_id,
            DbFile.category == FileCategory.system,
            DbFile.mime_type == "application/x-directory",
            DbFile.folder_path == folder_path,
        )
        .limit(1)
    ).scalar_one_or_none()
    if marker is None:
        return
    marker.updated_at = _db_now(db) + timedelta(seconds=_UPLOAD_SETTLE_SECONDS)
    db.add(marker)


def _case_folder_lock_k2(case_id: uuid.UUID) -> int:
    import zlib

    return zlib.crc32(case_id.bytes) & 0x7FFFFFFF


def _lock_case_folder_ops(db: Session, case_id: uuid.UUID, *, blocking: bool = True) -> None:
    """Serialize folder mutations per matter (PostgreSQL transaction-scoped advisory lock)."""
    from sqlalchemy import text

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    k2 = _case_folder_lock_k2(case_id)
    if blocking:
        db.execute(
            text("SELECT pg_advisory_xact_lock(:k1, :k2)"),
            {"k1": _FOLDER_OPS_LOCK_KEY1, "k2": k2},
        )
        return
    got = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
        {"k1": _FOLDER_OPS_LOCK_KEY1, "k2": k2},
    ).scalar()
    if not got:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FOLDER_BUSY_DETAIL)


def _try_lock_case_folder_ops_session(db: Session, case_id: uuid.UUID) -> bool:
    """Non-blocking session-level lock; shares the CL-09 key space with xact locks.

    Held across streaming so a concurrent folder delete cannot commit mid-upload and then
    remove a just-created file after HTTP 201. Caller must ``_unlock_case_folder_ops_session``.
    """
    from sqlalchemy import text

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    k2 = _case_folder_lock_k2(case_id)
    return bool(
        db.execute(
            text("SELECT pg_try_advisory_lock(:k1, :k2)"),
            {"k1": _FOLDER_OPS_LOCK_KEY1, "k2": k2},
        ).scalar()
    )


def _unlock_case_folder_ops_session(db: Session, case_id: uuid.UUID) -> None:
    from sqlalchemy import text

    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    k2 = _case_folder_lock_k2(case_id)
    db.execute(
        text("SELECT pg_advisory_unlock(:k1, :k2)"),
        {"k1": _FOLDER_OPS_LOCK_KEY1, "k2": k2},
    )


def _folder_destination_exists(db: Session, case_id: uuid.UUID, folder_path: str) -> bool:
    """True when root, or any file/marker still exists at or under ``folder_path``."""
    if not folder_path:
        return True
    prefix = folder_path
    like = f"{prefix}/%"
    row = db.execute(
        select(DbFile.id)
        .where(
            DbFile.case_id == case_id,
            or_(DbFile.folder_path == prefix, DbFile.folder_path.like(like)),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def _prepare_upload_folder(db: Session, case_id: uuid.UUID, folder: str) -> str:
    """Normalize folder and take a non-blocking folder-ops lock when uploading into a folder (CL-09)."""
    try:
        normalized = sanitize_folder_path(folder)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if normalized:
        _lock_case_folder_ops(db, case_id, blocking=False)
        if not _folder_destination_exists(db, case_id, normalized):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FOLDER_GONE_DETAIL)
    return normalized


def _folder_marker_exists(db: Session, case_id: uuid.UUID, folder_path: str) -> bool:
    row = db.execute(
        select(DbFile.id)
        .where(
            DbFile.case_id == case_id,
            DbFile.category == FileCategory.system,
            DbFile.mime_type == "application/x-directory",
            DbFile.folder_path == folder_path,
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def _insert_folder_marker(db: Session, case_id: uuid.UUID, user_id: uuid.UUID, folder_path: str) -> DbFile:
    """Persist a 0-byte system row so an otherwise-empty folder remains visible in the UI."""
    folder_name = folder_path.split("/")[-1].strip() or "Folder"
    file_id = uuid.uuid4()
    paths = case_file_paths(
        case_id=case_id,
        file_id=file_id,
        original_filename=folder_name,
        folder_path=folder_path,
    )
    with paths.abs_path.open("wb") as f:
        f.write(b"")
    row = DbFile(
        id=file_id,
        case_id=case_id,
        owner_id=user_id,
        category=FileCategory.system,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        is_pinned=False,
        original_filename=folder_name,
        mime_type="application/x-directory",
        size_bytes=0,
        version=1,
        checksum=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    return row


def _ensure_folder_marker_if_empty(
    db: Session,
    case_id: uuid.UUID,
    user_id: uuid.UUID,
    folder_path: str,
) -> None:
    """Folders created implicitly (files only, no marker) vanish when emptied unless we add a marker."""
    try:
        normalized = sanitize_folder_path(folder_path)
    except ValueError:
        return
    if not normalized:
        return
    if _folder_has_non_system_content(db, case_id, normalized):
        return
    if _folder_marker_exists(db, case_id, normalized):
        return
    ensure_files_root()
    _insert_folder_marker(db, case_id, user_id, normalized)
    db.commit()


def create_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderCreate,
    user: User,
    db: Session,
) -> dict:
    require_case_access(case_id, user, db)
    ensure_files_root()

    try:
        folder_path = sanitize_folder_path(payload.folder_path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if _folder_marker_exists(db, case_id, folder_path):
        return {"folder_path": folder_path}

    row = _insert_folder_marker(db, case_id, user.id, folder_path)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.folder.create",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), "folder_path": row.folder_path, "folder_name": row.original_filename},
    )
    db.commit()
    db.refresh(row)

    return {"folder_path": row.folder_path}


def rename_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderRenameUpdate,
    user: User,
    db: Session,
) -> dict:
    try:
        old_path = sanitize_folder_path(payload.old_folder_path)
        new_path = sanitize_folder_path(payload.new_folder_path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not old_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot rename Root")
    if old_path == new_path:
        return {"old_folder_path": old_path, "new_folder_path": new_path}

    require_case_access(case_id, user, db)
    ensure_files_root()
    from app.file_storage import FILES_ROOT

    # Serialize folder renames per matter so concurrent races cannot 500 on shutil.move (CL-05).
    _lock_case_folder_ops(db, case_id, blocking=True)

    old_prefix = old_path
    old_like = f"{old_prefix}/%"

    rows = list(
        db.execute(
            select(DbFile).where(
                (DbFile.case_id == case_id)
                & ((DbFile.folder_path == old_prefix) | (DbFile.folder_path.like(old_like)))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Folder was already renamed or no longer exists.",
        )

    moving_ids = [r.id for r in rows]
    raise_if_files_checked_out(
        db,
        [r.id for r in rows if r.category != FileCategory.system],
        action="rename this folder",
    )

    dest_conflict = (
        db.execute(
            select(DbFile.id)
            .where(
                DbFile.case_id == case_id,
                ~DbFile.id.in_(moving_ids),
                (DbFile.folder_path == new_path) | (DbFile.folder_path.like(f"{new_path}/%")),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    if dest_conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A folder or files already exist at the destination path.",
        )

    new_last = new_path.split("/")[-1].strip() if new_path else ""
    if not new_last:
        new_last = "Folder"

    try:
        for row in rows:
            old_fp = row.folder_path or ""
            relative = ""
            if old_fp == old_prefix:
                relative = ""
            elif old_fp.startswith(f"{old_prefix}/"):
                relative = old_fp[len(old_prefix) + 1 :]
            else:
                continue

            updated_fp = new_path + (f"/{relative}" if relative else "")

            updated_original = row.original_filename
            if row.category == FileCategory.system and row.folder_path == old_prefix:
                updated_original = new_last

            new_paths = case_file_paths(
                case_id=case_id,
                file_id=row.id,
                original_filename=updated_original,
                folder_path=updated_fp,
            )

            old_abs = (FILES_ROOT / row.storage_path).resolve()
            new_abs = new_paths.abs_path
            if old_abs.exists() and str(old_abs) != str(new_abs):
                shutil.move(str(old_abs), str(new_abs))

            row.storage_path = new_paths.rel_path
            row.folder_path = updated_fp
            if updated_original != row.original_filename:
                row.original_filename = updated_original
            row.updated_at = datetime.utcnow()
            db.add(row)
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Folder could not be renamed; it may have been moved by another user.",
        ) from exc

    from app.portal_service import rename_portal_grants_for_folder

    rename_portal_grants_for_folder(db, case_id=case_id, old_folder_path=old_path, new_folder_path=new_path)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.folder.rename",
        entity_type="case",
        entity_id=str(case_id),
        meta={"old_folder_path": old_path, "new_folder_path": new_path},
    )
    db.commit()

    return {"old_folder_path": old_path, "new_folder_path": new_path}


def delete_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderDeleteUpdate,
    user: User,
    db: Session,
) -> dict:
    folder_path = sanitize_folder_path(payload.folder_path)
    if not folder_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete Root")

    require_case_access(case_id, user, db)
    ensure_files_root()
    from app.file_storage import FILES_ROOT

    # Stamp request start before the lock so a concurrent upload that commits first
    # is visible as "newer than this delete" (CL-09) — then return 409 instead of
    # removing the just-created object after the uploader already received 201.
    request_started_at = _db_now(db)

    # Non-blocking: concurrent upload-into-folder gets 409 instead of 201-then-deleted (CL-09).
    _lock_case_folder_ops(db, case_id, blocking=False)

    prefix = folder_path
    like = f"{prefix}/%"

    rows = db.execute(
        select(DbFile).where((DbFile.case_id == case_id) & ((DbFile.folder_path == prefix) | (DbFile.folder_path.like(like))))
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_FOLDER_ALREADY_DELETED_DETAIL,
        )

    # Settle window: folder marker.updated_at held in the future after upload (CL-09).
    marker = next(
        (
            r
            for r in rows
            if r.category == FileCategory.system
            and r.mime_type == "application/x-directory"
            and r.folder_path == folder_path
        ),
        None,
    )
    now = _db_now(db)
    if marker is not None:
        marker_until = _as_utc(marker.updated_at)
        if marker_until is not None and marker_until > now:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_FOLDER_UPLOAD_SETTLING_DETAIL,
            )

    # Recent-upload settle window (CL-09): conflict if any document was created within
    # the last few seconds, covering upload-then-delete interleavings where the upload
    # finished just before this delete stamped request_started_at.
    settle_cutoff = now - timedelta(seconds=_UPLOAD_SETTLE_SECONDS)
    recent_upload = [
        r
        for r in rows
        if r.category != FileCategory.system
        and (created := _as_utc(r.created_at)) is not None
        and created > settle_cutoff
    ]
    if recent_upload:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_FOLDER_UPLOAD_SETTLING_DETAIL,
        )

    newer = [
        r
        for r in rows
        if r.category != FileCategory.system
        and (created := _as_utc(r.created_at)) is not None
        and request_started_at is not None
        and created > request_started_at
    ]
    if newer:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_FOLDER_MODIFIED_DURING_DELETE_DETAIL,
        )

    raise_if_files_checked_out(
        db,
        [r.id for r in rows if r.category != FileCategory.system],
        action="delete this folder",
    )

    # Delete physical files first (best effort).
    for row in rows:
        abs_path = (FILES_ROOT / row.storage_path).resolve()
        try:
            if abs_path.exists():
                abs_path.unlink()
        except Exception:
            # Avoid hard failing on filesystem inconsistencies.
            pass

    for row in rows:
        db.delete(row)
    removed_grants = 0
    from app.portal_service import revoke_portal_grants_for_deleted_folder

    removed_grants = revoke_portal_grants_for_deleted_folder(db, case_id=case_id, folder_path=folder_path)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.folder.delete",
        entity_type="case",
        entity_id=str(case_id),
        meta={"folder_path": folder_path, "deleted_count": len(rows), "portal_grants_removed": removed_grants},
    )
    db.commit()

    return {"folder_path": folder_path, "deleted_count": len(rows)}


def move_case_folder(
    case_id: uuid.UUID,
    payload: CaseFolderMoveUpdate,
    user: User,
    db: Session,
) -> dict:
    # Move keeps the folder leaf name; only the parent path changes.
    old_path = sanitize_folder_path(payload.old_folder_path)
    if not old_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot move Root")
    parts = [p for p in old_path.split("/") if p]
    leaf = parts[-1]
    new_parent = sanitize_folder_path(payload.new_parent_path)

    new_path = f"{new_parent}/{leaf}" if new_parent else leaf
    return rename_case_folder(
        case_id=case_id,
        payload=CaseFolderRenameUpdate(old_folder_path=old_path, new_folder_path=new_path),
        user=user,
        db=db,
    )
