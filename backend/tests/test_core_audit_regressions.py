"""Failure-path regressions from the Core architecture audit; synthetic data only."""
import asyncio
import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy import select, func

from app import file_storage
from app.db import SessionLocal
from app.models import File, FileCategory, Precedent, PrecedentKind, DocumentRecovery, AuditEvent
from tests.ledger_test_helpers import add_user, add_case


@pytest.fixture
def audit_db():
    with SessionLocal() as db:
        if db.bind.dialect.name != 'postgresql':
            pytest.skip('Requires isolated migrated PostgreSQL')
        yield db
        db.rollback()


def test_precedent_survives_lost_commit_ack(audit_db, tmp_path, monkeypatch):
    from app.routers import precedents
    db = audit_db
    admin = add_user(db, email='audit-' + uuid.uuid4().hex + '@example.test')
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    original = db.commit
    def commit_then_disconnect():
        original()
        raise ConnectionError('synthetic lost COMMIT acknowledgement')
    monkeypatch.setattr(db, 'commit', commit_then_disconnect)
    reference = 'AUDIT' + uuid.uuid4().hex[:12].upper()
    upload = UploadFile(io.BytesIO(b'synthetic precedent bytes'), filename='audit.txt',
                        headers=Headers({'content-type': 'text/plain'}))
    with pytest.raises(ConnectionError):
        precedents.upload_precedent(upload=upload, name='Audit synthetic', reference=reference,
            kind=PrecedentKind.document, matter_head_type_id=precedents.GLOBAL_SCOPE,
            matter_sub_type_id=precedents.GLOBAL_SCOPE, category_id=precedents.GLOBAL_SCOPE, admin=admin, db=db)
    with SessionLocal() as reader:
        precedent = reader.scalar(select(Precedent).where(Precedent.reference == reference))
        assert precedent is not None
        row = reader.get(File, precedent.file_id)
        assert (tmp_path / row.storage_path).read_bytes() == b'synthetic precedent bytes'


def test_failed_commit_retains_candidate_and_sync_failure_does_not_commit(tmp_path, monkeypatch):
    from app import document_durability
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    path = tmp_path / 'candidate.txt'; path.write_bytes(b'synthetic')
    calls = []
    def failed_commit():
        calls.append('commit')
        raise ConnectionError('no acknowledgement')
    with pytest.raises(ConnectionError):
        file_storage.commit_keeping_stored_file(SimpleNamespace(commit=failed_commit), path)
    assert path.read_bytes() == b'synthetic'
    def failed_sync(*args): raise OSError('disk error')
    monkeypatch.setattr(document_durability, 'sync_path', failed_sync)
    with pytest.raises(OSError):
        file_storage.commit_keeping_stored_file(SimpleNamespace(commit=failed_commit), path)
    assert calls == ['commit']


@pytest.mark.parametrize('name,mime,category', [
    ('agreement.pdf', 'application/pdf', FileCategory.case_document),
    ('agreement.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', FileCategory.case_document),
    ('marker.txt', 'text/plain', FileCategory.system),
    ('template.txt', 'text/plain', FileCategory.precedent),
    ('mislabelled.txt', 'application/pdf', FileCategory.case_document),
    ('mislabelled.pdf', 'text/plain', FileCategory.case_document),
])
def test_comment_rejects_other_file_types_without_side_effects(audit_db, tmp_path, monkeypatch, name, mime, category):
    from app import case_file_mutate_service as service
    from app.routers.files import update_comment_file
    from app.schemas import CommentFileUpdate
    db = audit_db
    user = add_user(db, email='audit-' + uuid.uuid4().hex + '@example.test')
    case = add_case(db, fee_earner_user_id=user.id)
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr(service, 'FILES_ROOT', tmp_path)
    path = tmp_path / name; path.write_bytes(b'synthetic original')
    row = File(id=uuid.uuid4(), case_id=case.id, owner_id=user.id, category=category,
        storage_path=name, original_filename=name, folder_path='', mime_type=mime, size_bytes=18, version=1)
    db.add(row); db.commit()
    before = db.scalar(select(func.count()).select_from(AuditEvent))
    with pytest.raises(HTTPException) as error:
        update_comment_file(case_id=case.id, file_id=row.id,
            payload=CommentFileUpdate(text='Replacement'), user=user, db=db)
    assert error.value.status_code == 400
    db.refresh(row)
    assert (row.original_filename, row.storage_path, row.mime_type, row.version) == (name, name, mime, 1)
    assert path.read_bytes() == b'synthetic original'
    assert list(tmp_path.iterdir()) == [path]
    assert db.scalar(select(func.count()).select_from(DocumentRecovery).where(DocumentRecovery.file_id == row.id)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_valid_comment_keeps_recovery_and_updates_text(audit_db, tmp_path, monkeypatch):
    from app import case_file_mutate_service as service
    from app.schemas import CommentFileUpdate
    db = audit_db
    user = add_user(db, email='audit-' + uuid.uuid4().hex + '@example.test')
    case = add_case(db, fee_earner_user_id=user.id)
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr(service, 'FILES_ROOT', tmp_path)
    path = tmp_path / 'comment.TXT'; path.write_bytes(b'original')
    row = File(id=uuid.uuid4(), case_id=case.id, owner_id=user.id, category=FileCategory.case_document,
        storage_path=path.name, original_filename=path.name, folder_path='',
        mime_type='text/plain; charset=utf-8', size_bytes=8, version=1)
    db.add(row); db.commit()
    service.update_comment_file(case.id, row.id, CommentFileUpdate(text='Changed comment'), user, db)
    db.refresh(row)
    assert row.version == 2 and row.original_filename == 'Changed comment.txt'
    assert (tmp_path / row.storage_path).read_bytes() == b'Changed comment'
    assert path.read_bytes() == b'original'
    assert db.scalar(select(func.count()).select_from(DocumentRecovery).where(DocumentRecovery.file_id == row.id)) == 1


class CountingUpload:
    def __init__(self, length):
        self.remaining = length
        self.consumed = 0
        self.reads = []
    async def read(self, size=-1):
        assert 0 < size <= 64 * 1024
        self.reads.append(size)
        count = min(size, self.remaining)
        self.remaining -= count; self.consumed += count
        return b'x' * count


def test_portal_upload_rejects_oversize_before_storage(monkeypatch):
    from app import portal_form_service as service
    from app.models import PortalFormSubmissionStatus, PortalFormFieldType
    upload = CountingUpload(100 * 1024 * 1024)
    db = SimpleNamespace(get=lambda *a: SimpleNamespace(id=uuid.uuid4()))
    submission = SimpleNamespace(status=PortalFormSubmissionStatus.pending, template_id=uuid.uuid4())
    monkeypatch.setattr(service, 'load_template_fields', lambda *a: [
        SimpleNamespace(field_key='attachment', field_type=PortalFormFieldType.file)])
    def forbidden(*args): pytest.fail('oversized upload reached filesystem')
    monkeypatch.setattr(service, 'ensure_files_root', forbidden)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.upload_submission_file(db, submission=submission,
            field_key='attachment', upload=upload, contact=None))
    assert error.value.status_code == 413
    assert upload.consumed == 25 * 1024 * 1024 + 1


@pytest.mark.parametrize('length', [0, 1, 65536, 25 * 1024 * 1024])
def test_portal_upload_boundary_reads_are_bounded(length):
    from app.portal_form_service import _read_submission_upload
    upload = CountingUpload(length)
    assert asyncio.run(_read_submission_upload(upload)) == b'x' * length
    assert upload.consumed == length


def test_comment_checks_type_after_locked_reload(audit_db, tmp_path, monkeypatch):
    from app import case_file_mutate_service as service
    from app.schemas import CommentFileUpdate
    db = audit_db
    user = add_user(db, email='audit-' + uuid.uuid4().hex + '@example.test')
    case = add_case(db, fee_earner_user_id=user.id)
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr(service, 'FILES_ROOT', tmp_path)
    path = tmp_path / 'original.txt'; path.write_bytes(b'original')
    row = File(id=uuid.uuid4(), case_id=case.id, owner_id=user.id, category=FileCategory.case_document,
        storage_path=path.name, original_filename=path.name, folder_path='', mime_type='text/plain', size_bytes=8, version=1)
    db.add(row); db.commit()
    identity = row.id
    real_lock = service.lock_document
    def concurrent_change(session, stale):
        # Simulate replacement after the initial identity-map read, before FOR UPDATE.
        with SessionLocal() as other:
            current = other.get(File, identity)
            current.original_filename = 'replacement.pdf'
            current.mime_type = 'application/pdf'
            other.commit()
        return real_lock(session, stale)
    monkeypatch.setattr(service, 'lock_document', concurrent_change)
    with pytest.raises(HTTPException) as error:
        service.update_comment_file(case.id, row.id, CommentFileUpdate(text='Must not replace'), user, db)
    assert error.value.status_code == 400
    assert path.read_bytes() == b'original'
    assert list(tmp_path.iterdir()) == [path]


def test_empty_portal_upload_remains_422(monkeypatch):
    from app import portal_form_service as service
    from app.models import PortalFormSubmissionStatus, PortalFormFieldType
    db = SimpleNamespace(get=lambda *a: SimpleNamespace(id=uuid.uuid4()))
    submission = SimpleNamespace(status=PortalFormSubmissionStatus.pending, template_id=uuid.uuid4())
    monkeypatch.setattr(service, 'load_template_fields', lambda *a: [
        SimpleNamespace(field_key='attachment', field_type=PortalFormFieldType.file)])
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.upload_submission_file(db, submission=submission,
            field_key='attachment', upload=CountingUpload(0), contact=None))
    assert error.value.status_code == 422
