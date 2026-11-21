"""Operator recovery of retained case documents. No background cleanup is performed."""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import DateTime, Uuid, select

from app.audit import log_event
from app.document_durability import lock_document, safe_path, stage_document_bytes, sync_path
from app.models import Case, DocumentRecovery, File, FileCategory, User, UserRole


def verified_bytes(record: DocumentRecovery, root: Path) -> bytes:
    if record.storage_path is None:
        if record.snapshot.get('mime_type') == 'application/x-directory':
            return b''
        raise HTTPException(409, 'This recovery record has no retained bytes; use a verified backup.')
    data = safe_path(root, record.storage_path).read_bytes()
    if hashlib.sha256(data).hexdigest() != record.checksum:
        raise HTTPException(409, 'Recovery checksum mismatch; no document was restored.')
    return data


def _snapshot_values(record):
    values = dict(record.snapshot)
    for col in File.__table__.columns:
        value = values.get(col.name)
        if value is not None and isinstance(col.type, Uuid):
            values[col.name] = uuid.UUID(value)
        elif value is not None and isinstance(col.type, DateTime):
            values[col.name] = datetime.fromisoformat(value)
    values.update(oo_force_save_pending=False, oo_save_attempt_id=None,
                  oo_save_document_key=None, oo_save_state=None, oo_save_base_version=None)
    return values


def restore_document(db, recovery_id, *, root, actor_id, expected_version=None):
    """Stage recovery in caller's transaction. Restore deleted attachment groups together.

    Only case documents are reinstated automatically: precedent/firm links and external
    sharing grants require separate review and are never silently reconstructed.
    """
    actor = db.get(User, actor_id)
    if actor is None or not actor.is_active or actor.role != UserRole.admin:
        raise HTTPException(403, 'Recovery requires an active administrator.')
    record = db.execute(select(DocumentRecovery).where(DocumentRecovery.id == recovery_id)
                        .with_for_update()).scalar_one_or_none()
    if record is None:
        raise HTTPException(404, 'Recovery record not found')
    records = [record]
    if record.kind == 'deleted':
        records = list(db.scalars(select(DocumentRecovery).where(
            DocumentRecovery.group_id == record.group_id).order_by(DocumentRecovery.id).with_for_update()))
    # Verify every archive and relationship before publishing any pointer.
    data_by_id = {r.id: verified_bytes(r, Path(root)) for r in records}
    values_by_id = {r.file_id: _snapshot_values(r) for r in records}
    for values in values_by_id.values():
        if values['case_id'] is None or db.get(Case, values['case_id']) is None:
            raise HTTPException(409, 'Automatic restore requires an existing matter. Export retained bytes for manual recovery.')
        if db.get(User, values['owner_id']) is None:
            raise HTTPException(409, 'The original document owner no longer exists.')
    restored = []
    pending = list(records)
    while pending:
        progressed = False
        for item in list(pending):
            values = values_by_id[item.file_id]
            parent_id = values.get('parent_file_id')
            if parent_id and db.get(File, parent_id) is None:
                if parent_id in {r.file_id for r in pending}:
                    continue
                raise HTTPException(409, 'Restore the parent document first.')
            row = db.get(File, item.file_id)
            if item.kind == 'deleted':
                if row is not None:
                    raise HTTPException(409, 'A document with this ID already exists; nothing was overwritten.')
                duplicate = db.scalar(select(File.id).where(
                    File.case_id == values['case_id'], File.folder_path == values['folder_path'],
                    File.original_filename == values['original_filename']))
                if duplicate:
                    raise HTTPException(409, 'A document with this name already exists in the destination folder.')
                relative = str(Path('.versions') / str(item.file_id) / str(uuid.uuid4()) / Path(values['original_filename']).name)
                path = safe_path(root, relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as stream:
                    stream.write(data_by_id[item.id])
                sync_path(path, Path(root).resolve())
                values.update(storage_path=relative, size_bytes=len(data_by_id[item.id]),
                              checksum=hashlib.sha256(data_by_id[item.id]).hexdigest(),
                              updated_at=datetime.now(timezone.utc))
                row = File(**values)
                db.add(row)
            else:
                if row is None or expected_version is None:
                    raise HTTPException(409, 'Version recovery requires an existing document and --expected-version.')
                row = lock_document(db, row, expected_version=expected_version)
                from app.desktop_edit_session import raise_if_files_checked_out
                raise_if_files_checked_out(db, [row.id], action='restore')
                stage_document_bytes(db, row, data_by_id[item.id], root=root, kind='restore',
                                     allow_missing_current=True)
                row.original_filename = values['original_filename']
                row.mime_type = values['mime_type']
                row.version = (row.version or 1) + 1
                row.oo_save_state = 'failed'
                row.oo_force_save_pending = False
                row.updated_at = datetime.now(timezone.utc)
            db.flush()
            log_event(db, actor_user_id=actor_id, action='case.file.recover', entity_type='file',
                      entity_id=str(row.id), meta={'recovery_id': str(item.id), 'kind': item.kind})
            restored.append(str(row.id))
            pending.remove(item)
            progressed = True
        if not progressed:
            raise HTTPException(409, 'Recovery parent relationships contain a cycle.')
    return restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    listing = sub.add_parser('list')
    listing.add_argument('--file-id', type=uuid.UUID, required=True)
    export = sub.add_parser('export')
    export.add_argument('--recovery-id', type=uuid.UUID, required=True)
    export.add_argument('--output', type=Path, required=True)
    restore = sub.add_parser('restore')
    restore.add_argument('--recovery-id', type=uuid.UUID, required=True)
    restore.add_argument('--actor-id', type=uuid.UUID, required=True)
    restore.add_argument('--expected-version', type=int)
    args = parser.parse_args()
    from app.db import SessionLocal
    from app.file_storage import FILES_ROOT
    with SessionLocal() as db:
        if args.command == 'list':
            rows = db.scalars(select(DocumentRecovery).where(DocumentRecovery.file_id == args.file_id)
                              .order_by(DocumentRecovery.created_at.desc()))
            print(json.dumps([{'id': str(r.id), 'group_id': str(r.group_id), 'kind': r.kind,
                               'created_at': str(r.created_at), 'version': r.snapshot.get('version'),
                               'filename': r.snapshot.get('original_filename'), 'checksum': r.checksum}
                              for r in rows], indent=2))
        elif args.command == 'export':
            record = db.get(DocumentRecovery, args.recovery_id)
            if record is None:
                raise HTTPException(404, 'Recovery record not found')
            data = verified_bytes(record, FILES_ROOT)
            with args.output.open('xb') as stream:
                stream.write(data)
            sync_path(args.output.resolve(), args.output.parent.resolve())
            print(json.dumps({'exported': str(args.output), 'checksum': record.checksum}))
        else:
            try:
                ids = restore_document(db, args.recovery_id, root=FILES_ROOT,
                                       actor_id=args.actor_id, expected_version=args.expected_version)
                db.commit()
            except Exception:
                db.rollback()
                raise
            print(json.dumps({'restored_file_ids': ids}))


if __name__ == '__main__':
    main()
