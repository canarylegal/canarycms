"""Run only against the disposable migrated PostgreSQL core-workflow stack."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db import SessionLocal
from app.document_durability import lock_document, stage_document_bytes
from app.document_recovery import restore_document
from app.models import DocumentRecovery, File, FileCategory, User
from app import case_file_mutate_service as service
from tests.ledger_test_helpers import add_user, add_case


def test_concurrent_save_rejects_losing_version(db, tmp_path):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('requires disposable PostgreSQL')
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    fid = uuid.uuid4()
    row = File(id=fid, case_id=case.id, owner_id=user.id, category=FileCategory.case_document,
               folder_path='', original_filename='concurrent.txt', storage_path='concurrent.txt',
               mime_type='text/plain', size_bytes=8, version=1)
    (tmp_path / row.storage_path).write_bytes(b'original')
    db.add(row)
    db.commit()
    locked, contender_started = Event(), Event()
    def first_save():
        with SessionLocal() as session:
            item = lock_document(session, session.get(File, fid), expected_version=1)
            locked.set()
            assert contender_started.wait(10)
            stage_document_bytes(session, item, b'winner', root=tmp_path)
            item.version = 2
            session.commit()
    def second_save():
        assert locked.wait(10)
        with SessionLocal() as session:
            item = session.get(File, fid)
            contender_started.set()
            with pytest.raises(HTTPException) as error:
                lock_document(session, item, expected_version=1)
            assert error.value.status_code == 409
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(first_save), pool.submit(second_save)
        first.result(15)
        second.result(15)
    db.refresh(row)
    assert row.version == 2
    assert (tmp_path / row.storage_path).read_bytes() == b'winner'


def test_cascaded_deletion_group_restores_parent_and_attachment(db, tmp_path, monkeypatch):
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('requires disposable PostgreSQL')
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    parent_id, child_id = uuid.uuid4(), uuid.uuid4()
    for fid, name, parent in [(parent_id, 'mail.eml', None), (child_id, 'attachment.txt', parent_id)]:
        (tmp_path / name).write_bytes(name.encode())
        db.add(File(id=fid, case_id=case.id, owner_id=user.id, category=FileCategory.case_document,
                    folder_path='', original_filename=name, storage_path=name, mime_type='text/plain',
                    size_bytes=len(name), version=1, parent_file_id=parent))
        db.commit()
    monkeypatch.setattr(service, 'FILES_ROOT', tmp_path)
    service.delete_case_file(case.id, parent_id, user, db)
    db.expire_all()
    assert db.get(File, parent_id) is None and db.get(File, child_id) is None
    record = db.scalar(select(DocumentRecovery).where(DocumentRecovery.file_id == parent_id))
    ids = restore_document(db, record.id, root=tmp_path, actor_id=user.id)
    db.commit()
    assert set(ids) == {str(parent_id), str(child_id)}
    assert db.get(File, child_id).parent_file_id == parent_id
    assert (tmp_path / db.get(File, child_id).storage_path).read_bytes() == b'attachment.txt'
