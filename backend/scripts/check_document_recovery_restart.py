"""Retain/delete before a disposable restart; recover from another process afterwards."""
import io
import json
import os
import sys
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select

from app.db import SessionLocal
from app.document_durability import lock_document, stage_document_bytes
from app.document_recovery import restore_document
from app.file_upload_service import upload_case_file
from app.case_file_mutate_service import delete_case_file
from app.models import User, Case, File, DocumentRecovery

if os.getenv('CANARY_TEST_FIXTURE') != '1' or os.getenv('POSTGRES_DB') != 'canary_core_test':
    raise SystemExit('Requires the disposable core fixture')
root = Path(os.environ['FILES_ROOT'])
manifest = root / '.document-recovery-test.json'
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == 'core.approver@example.com'))
    matter = db.scalar(select(Case).where(Case.case_number == '900001'))
    assert user is not None and matter is not None
    if sys.argv[1] == 'prepare':
        assert not manifest.exists()
        saved = upload_case_file(matter.id, UploadFile(io.BytesIO(b'previous version'), filename='restart-version.txt'), user=user, db=db)
        row = lock_document(db, db.get(File, uuid.UUID(saved['id'])))
        stage_document_bytes(db, row, b'current version', root=root)
        row.version += 1
        db.commit()
        prior = db.scalar(select(DocumentRecovery).where(DocumentRecovery.file_id == row.id))
        deleted = upload_case_file(matter.id, UploadFile(io.BytesIO(b'deleted bytes'), filename='restart-deleted.txt'), user=user, db=db)
        delete_case_file(matter.id, uuid.UUID(deleted['id']), user, db)
        archive = db.scalar(select(DocumentRecovery).where(DocumentRecovery.file_id == uuid.UUID(deleted['id'])))
        manifest.write_text(json.dumps({'saved_id': saved['id'], 'deleted_id': deleted['id'],
                                       'version_archive': str(prior.id), 'delete_archive': str(archive.id)}))
        print('Prepared retained version and deletion')
    elif sys.argv[1] == 'verify':
        state = json.loads(manifest.read_text())
        saved = db.get(File, uuid.UUID(state['saved_id']))
        assert saved.version == 2 and (root / saved.storage_path).read_bytes() == b'current version'
        assert db.get(File, uuid.UUID(state['deleted_id'])) is None
        restore_document(db, uuid.UUID(state['version_archive']), root=root, actor_id=user.id, expected_version=2)
        restore_document(db, uuid.UUID(state['delete_archive']), root=root, actor_id=user.id)
        db.commit()
        assert (root / saved.storage_path).read_bytes() == b'previous version'
        deleted = db.get(File, uuid.UUID(state['deleted_id']))
        assert (root / deleted.storage_path).read_bytes() == b'deleted bytes'
        print('Verified version and deletion recovery after backend restart')
    else:
        raise SystemExit('Use prepare or verify')
