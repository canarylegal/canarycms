"""Recoverable File mutations. Bytes are immutable; DB transactions publish pointers."""
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from app.models import File, DocumentRecovery


def safe_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(500, 'Invalid document storage path')
    return path


def sync_path(path, root):
    with path.open('rb') as stream:
        os.fsync(stream.fileno())
    parent = path.parent
    while parent.is_relative_to(root):
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if parent == root:
            break
        parent = parent.parent


def lock_document(db, row, *, expected_version=None):
    locked = db.execute(select(File).where(File.id == row.id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if locked is None or (expected_version is not None and locked.version != expected_version):
        raise HTTPException(409, 'The document changed during this operation. Refresh and retry.')
    return locked


def retain_document(db, row, *, root, kind, group_id=None):
    """Archive bytes before mutation; commit the recovery record with its DB change."""
    root = Path(root).resolve()
    record_id = uuid.uuid4()
    snapshot = json.loads(json.dumps({column.name: getattr(row, column.name) for column in File.__table__.columns}, default=str))
    source = safe_path(root, row.storage_path)
    relative = None
    checksum = None
    if source.is_file():
        relative = str(Path('.recovery') / str(record_id) / Path(row.original_filename).name)
        target = safe_path(root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        sync_path(target, root)
        with target.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    record = DocumentRecovery(id=record_id, group_id=group_id or record_id, file_id=row.id,
        kind=kind, snapshot=snapshot, storage_path=relative, checksum=checksum)
    db.add(record)
    return record


def stage_document_bytes(db, row, data, *, root, kind='version', allow_missing_current=False):
    """Caller holds File row lock and commits metadata/audit together. Never unlink on rollback."""
    root = Path(root).resolve()
    if not allow_missing_current and not safe_path(root, row.storage_path).is_file():
        raise HTTPException(409, 'The current document bytes are missing. Restore the document before saving.')
    retain_document(db, row, root=root, kind=kind)
    relative = str(Path('.versions') / str(row.id) / str(uuid.uuid4()) / Path(row.original_filename).name)
    target = safe_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_path(target, root)
    row.storage_path = relative
    row.size_bytes = len(data)
    row.checksum = hashlib.sha256(data).hexdigest()
    # Do not remove the old path or .oo_backup: rollback/ambiguous commit remains safe.
    return target
