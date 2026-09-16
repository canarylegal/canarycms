"""Case file mutate helpers (pin, rename, comment, move, delete)."""

from __future__ import annotations

import shutil
import uuid
import zlib
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit import log_event
from app.case_folder_service import (
    _FILE_MOVE_CONFLICT_DETAIL,
    _FOLDER_GONE_DETAIL,
    _ensure_folder_marker_if_empty,
    _folder_destination_exists,
    _lock_case_folder_ops,
)
from app.deps import require_case_access
from app.desktop_edit_session import raise_if_files_checked_out
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root, sanitize_folder_path
from app.models import File as DbFile, FileCategory, User
from app.schemas import CaseFileMoveUpdate, CaseFileRenameUpdate, CommentFileUpdate, FilePinUpdate

_FILE_RENAME_CONFLICT_DETAIL = "File was renamed or moved by another user. Refresh and try again."
_FILE_RENAME_BUSY_DETAIL = "This file is being renamed by another user. Refresh and try again."
# Distinct from folder-ops / ledger pair lock namespaces.
_FILE_RENAME_LOCK_KEY1 = 582013715


def _file_rename_lock_k2(file_id: uuid.UUID) -> int:
    return zlib.crc32(file_id.bytes) & 0x7FFFFFFF


def _try_lock_file_rename(db: Session, file_id: uuid.UUID) -> None:
    """Non-blocking xact lock so concurrent renames cannot both return 200 (CL-19)."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    got = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
        {"k1": _FILE_RENAME_LOCK_KEY1, "k2": _file_rename_lock_k2(file_id)},
    ).scalar()
    if not got:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FILE_RENAME_BUSY_DETAIL)


def _normalized_file_suffix(name: str) -> str:
    return Path(name).suffix.lower()


def set_file_pin(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: FilePinUpdate,
    user: User,
    db: Session,
) -> dict:
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    row.is_pinned = payload.is_pinned
    db.add(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="file.pin",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), "is_pinned": payload.is_pinned, "filename": row.original_filename},
    )
    db.commit()
    db.refresh(row)

    return {"id": str(row.id), "is_pinned": row.is_pinned}


def rename_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: CaseFileRenameUpdate,
    user: User,
    db: Session,
) -> dict:
    require_case_access(case_id, user, db)
    # CL-19: compare-and-swap on the client-observed name so concurrent renames from the same
    # starting name cannot both return 200 (even if the loser reaches the server after the winner
    # commits). Try-lock reduces overlap; the expected-name check is the authoritative guard.
    expected_name = Path(payload.expected_original_filename).name
    if not expected_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid expected filename")

    _try_lock_file_rename(db, file_id)
    row = db.execute(
        select(DbFile).where(DbFile.id == file_id).with_for_update()
    ).scalar_one_or_none()
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if (row.original_filename or "") != expected_name:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FILE_RENAME_BUSY_DETAIL)
    if row.category == FileCategory.system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot rename folder markers here")

    raise_if_files_checked_out(db, [file_id], action="rename")

    new_name = Path(payload.original_filename).name
    if not new_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    old_ext = _normalized_file_suffix(row.original_filename or "")
    new_ext = _normalized_file_suffix(new_name)
    if old_ext != new_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renaming cannot change the file extension.",
        )

    old_filename = row.original_filename
    ensure_files_root()
    folder = row.folder_path or ""
    new_paths = case_file_paths(
        case_id=case_id,
        file_id=row.id,
        original_filename=new_name,
        folder_path=folder,
    )
    old_abs = (FILES_ROOT / row.storage_path).resolve()
    new_abs = new_paths.abs_path
    if str(old_abs) != str(new_abs):
        if not old_abs.is_file():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_FILE_RENAME_CONFLICT_DETAIL,
            )
        if new_abs.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_FILE_RENAME_CONFLICT_DETAIL,
            )
        shutil.move(str(old_abs), str(new_abs))

    row.storage_path = new_paths.rel_path
    row.folder_path = new_paths.folder_path
    row.original_filename = new_name
    row.updated_at = datetime.utcnow()
    db.add(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.rename",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "case_id": str(case_id),
            "old_filename": old_filename,
            "new_filename": row.original_filename,
        },
    )
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "original_filename": row.original_filename}


def update_comment_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: CommentFileUpdate,
    user: User,
    db: Session,
) -> dict:
    """Update the text content of a comment (.txt) file and auto-rename it from the first line."""
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    raise_if_files_checked_out(db, [file_id], action="edit")

    ensure_files_root()

    # Derive new filename from first line (≤80 chars)
    first_line = (payload.text.strip().split("\n")[0].strip() or "Comment")[:80]
    if len(first_line) == 80:
        first_line = first_line[:77] + "…"
    old_filename = row.original_filename
    new_name = first_line + ".txt"

    folder = row.folder_path or ""
    new_paths = case_file_paths(
        case_id=case_id,
        file_id=row.id,
        original_filename=new_name,
        folder_path=folder,
    )
    old_abs = (FILES_ROOT / row.storage_path).resolve()

    # Write new content
    encoded = payload.text.encode("utf-8")
    new_paths.abs_path.parent.mkdir(parents=True, exist_ok=True)
    new_paths.abs_path.write_bytes(encoded)

    # Remove old file if path changed
    if old_abs.exists() and str(old_abs) != str(new_paths.abs_path):
        try:
            old_abs.unlink()
        except OSError:
            pass

    row.storage_path = new_paths.rel_path
    row.folder_path = new_paths.folder_path
    row.original_filename = new_name
    row.size_bytes = len(encoded)
    row.updated_at = datetime.utcnow()
    db.add(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.comment.update",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "case_id": str(case_id),
            "old_filename": old_filename,
            "new_filename": row.original_filename,
        },
    )
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "original_filename": row.original_filename}


def move_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: CaseFileMoveUpdate,
    user: User,
    db: Session,
) -> dict:
    require_case_access(case_id, user, db)
    # Serialize against recursive folder delete on this matter (CL-12).
    _lock_case_folder_ops(db, case_id, blocking=False)
    row = db.execute(
        select(DbFile).where(DbFile.id == file_id).with_for_update()
    ).scalar_one_or_none()
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.category == FileCategory.system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot move folder markers here")

    # Move parent + its children (attachments) together so indentation/grouping stays consistent.
    children = (
        db.execute(
            select(DbFile)
            .where(DbFile.case_id == case_id, DbFile.parent_file_id == file_id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    rows_to_move = [row, *children]
    raise_if_files_checked_out(db, [r.id for r in rows_to_move], action="move")

    old_folder = row.folder_path or ""
    try:
        new_folder = sanitize_folder_path(payload.folder_path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if new_folder and not _folder_destination_exists(db, case_id, new_folder):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FOLDER_GONE_DETAIL)

    ensure_files_root()
    from sqlalchemy.orm.exc import StaleDataError

    try:
        for r in rows_to_move:
            new_paths = case_file_paths(
                case_id=case_id,
                file_id=r.id,
                original_filename=r.original_filename,
                folder_path=new_folder,
            )
            old_abs = (FILES_ROOT / r.storage_path).resolve()
            new_abs = new_paths.abs_path
            if str(old_abs) != str(new_abs):
                if not old_abs.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=_FILE_MOVE_CONFLICT_DETAIL,
                    )
                if new_abs.exists():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=_FILE_MOVE_CONFLICT_DETAIL,
                    )
                try:
                    shutil.move(str(old_abs), str(new_abs))
                except OSError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=_FILE_MOVE_CONFLICT_DETAIL,
                    ) from exc

            r.storage_path = new_paths.rel_path
            r.folder_path = new_paths.folder_path
            r.updated_at = datetime.utcnow()
            db.add(r)

        log_event(
            db,
            actor_user_id=user.id,
            action="case.file.move",
            entity_type="file",
            entity_id=str(row.id),
            meta={
                "case_id": str(case_id),
                "filename": row.original_filename,
                "old_folder_path": old_folder,
                "new_folder_path": row.folder_path,
            },
        )
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_FILE_MOVE_CONFLICT_DETAIL,
        ) from exc

    db.refresh(row)
    if old_folder:
        _ensure_folder_marker_if_empty(db, case_id, user.id, old_folder)
    return {"id": str(row.id), "folder_path": row.folder_path}


def _erase_case_file_tree(db: Session, case_id: uuid.UUID, file_id: uuid.UUID) -> DbFile | None:
    """Delete a case file (and child rows) from disk and database. Returns the parent row if deleted."""
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        return None
    ensure_files_root()
    rows_to_delete = [row]
    children = (
        db.execute(select(DbFile).where(DbFile.case_id == case_id, DbFile.parent_file_id == file_id)).scalars().all()
    )
    rows_to_delete.extend(children)
    raise_if_files_checked_out(db, [r.id for r in rows_to_delete], action="delete")
    for r in rows_to_delete:
        abs_path = (FILES_ROOT / r.storage_path).resolve()
        backup = Path(str(abs_path) + ".oo_backup")
        try:
            if backup.exists():
                backup.unlink()
        except Exception:
            pass
        try:
            if abs_path.exists():
                abs_path.unlink()
        except Exception:
            pass
    db.delete(row)
    db.commit()
    return row


def delete_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User,
    db: Session,
) -> None:
    require_case_access(case_id, user, db)
    deleted = _erase_case_file_tree(db, case_id, file_id)
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    old_folder = deleted.folder_path or ""
    if old_folder:
        _ensure_folder_marker_if_empty(db, case_id, user.id, old_folder)

    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.delete",
        entity_type="file",
        entity_id=str(file_id),
        meta={
            "case_id": str(case_id),
            "filename": deleted.original_filename,
            "folder_path": deleted.folder_path or "",
        },
    )
    return None
