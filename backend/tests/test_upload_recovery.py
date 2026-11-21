import io
import uuid

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func
from starlette.datastructures import Headers
from app import file_storage, file_upload_service as service
from app.models import AuditEvent, File, UploadReceipt, User
from tests.ledger_test_helpers import ledger_test_session, add_user, add_case


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    db = ledger_test_session()
    UploadReceipt.__table__.create(db.bind)
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr(service, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr('app.firm_module_runtime.process_document_uploaded', lambda *a, **k: None)
    case_id, user_id = case.id, user.id
    def upload(key, body=b'content', name='sample.txt', **kw):
        return service.upload_case_file(case_id, UploadFile(io.BytesIO(body), filename=name,
            headers=Headers({'content-type': 'application/octet-stream'})),
            idempotency_key=key, user=db.get(User, user_id), db=db, **kw)
    yield db, user, case, upload, tmp_path
    db.close()


def test_lost_response_replays_one_file_and_audit_after_new_session(uploads):
    db, user, case, upload, root = uploads
    key = uuid.uuid4()
    first = upload(key)
    db.close()  # a new DB transaction/identity map must recover the receipt
    second = upload(key)
    assert first == second
    assert db.scalar(select(func.count()).select_from(File)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'case.file.upload')) == 1
    assert len([p for p in root.rglob('*') if p.is_file()]) == 1


@pytest.mark.parametrize('change', [{'body': b'other'}, {'name': 'other.txt'}, {'notify_portal_contacts': True}, {'folder': 'Elsewhere'}])
def test_changed_retry_rejected_without_another_file(uploads, change):
    db, _, _, upload, _ = uploads
    key = uuid.uuid4(); upload(key)
    with pytest.raises(HTTPException) as err: upload(key, **change)
    assert err.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(File)) == 1


def test_deleted_upload_is_not_resurrected(uploads):
    db, _, _, upload, _ = uploads
    key = uuid.uuid4(); result = upload(key)
    db.delete(db.get(File, uuid.UUID(result['id']))); db.commit()
    with pytest.raises(HTTPException) as err: upload(key)
    assert err.value.status_code == 410


def test_receipt_cannot_bypass_revoked_access(uploads, monkeypatch):
    _, _, _, upload, _ = uploads
    key = uuid.uuid4(); upload(key)
    def denied(*args): raise HTTPException(403, 'revoked')
    monkeypatch.setattr(service, 'require_case_access', denied)
    with pytest.raises(HTTPException) as err: upload(key)
    assert err.value.status_code == 403


def test_failed_database_commit_cleans_file_and_can_retry(uploads, monkeypatch):
    db, _, _, upload, root = uploads
    commit = db.commit
    def fail(): raise RuntimeError('database unavailable')
    monkeypatch.setattr(db, 'commit', fail)
    key = uuid.uuid4()
    with pytest.raises(RuntimeError): upload(key)
    assert not [p for p in root.rglob('*') if p.is_file()]
    monkeypatch.setattr(db, 'commit', commit)
    upload(key)
    assert db.scalar(select(func.count()).select_from(File)) == 1


def test_commit_acknowledgement_loss_keeps_committed_bytes(uploads, monkeypatch):
    db, _, _, upload, root = uploads
    commit = db.commit
    def lose_ack():
        commit()
        raise RuntimeError('connection lost after commit')
    monkeypatch.setattr(db, 'commit', lose_ack)
    key = uuid.uuid4()
    with pytest.raises(RuntimeError): upload(key)
    monkeypatch.setattr(db, 'commit', commit)
    result = upload(key)
    row = db.get(File, uuid.UUID(result['id']))
    assert (root / row.storage_path).read_bytes() == b'content'
    assert db.scalar(select(func.count()).select_from(File)) == 1


def test_storage_failure_leaves_no_receipt_and_retries(uploads, monkeypatch):
    db, _, _, upload, root = uploads
    stream = service.stream_upload_to_path
    def fail(*a, **k): raise OSError('no space')
    monkeypatch.setattr(service, 'stream_upload_to_path', fail)
    key = uuid.uuid4()
    with pytest.raises(OSError): upload(key)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(UploadReceipt)) == 0
    monkeypatch.setattr(service, 'stream_upload_to_path', stream)
    upload(key)
    assert len([p for p in root.rglob('*') if p.is_file()]) == 1


def test_stream_interruption_removes_partial_file(tmp_path):
    class Broken:
        reads = 0
        def read(self, n):
            self.reads += 1
            if self.reads == 1: return b'first part'
            raise OSError('connection lost')
    with pytest.raises(OSError): file_storage.stream_upload_to_path(tmp_path/'doc', Broken(), max_bytes=100)
    assert not list(tmp_path.iterdir())


def test_large_file_is_streamed_and_limit_does_not_leave_receipt(uploads, monkeypatch):
    db, _, _, upload, _ = uploads
    monkeypatch.setattr('app.upload_receipts.max_upload_bytes', lambda: 8*1024*1024)
    key = uuid.uuid4()
    with pytest.raises(HTTPException) as err: upload(key, body=b'x'*(8*1024*1024+1))
    assert err.value.status_code == 413
    assert db.scalar(select(func.count()).select_from(UploadReceipt)) == 0
    assert upload(key, body=b'x'*(8*1024*1024))['size_bytes'] == 8*1024*1024


def test_attachment_retry_keeps_parent_and_child_unique(uploads):
    db, _, _, upload, _ = uploads
    parent = upload(uuid.uuid4(), name='email.eml', body=b'From: sender@example.com\r\nSubject: mail\r\n\r\nHello')
    key = uuid.uuid4()
    child = upload(key, parent_file_id=uuid.UUID(parent['id']))
    assert upload(key, parent_file_id=uuid.UUID(parent['id'])) == child
    assert db.get(File, uuid.UUID(child['id'])).parent_file_id == uuid.UUID(parent['id'])
    assert db.scalar(select(func.count()).select_from(File)) == 2


def test_same_key_in_another_user_scope_cannot_reveal_the_first_receipt(uploads):
    db, _, case, upload, _ = uploads
    key = uuid.uuid4(); first = upload(key)
    other = add_user(db)
    second = service.upload_case_file(case.id, UploadFile(io.BytesIO(b'other user'), filename='other.txt'),
        idempotency_key=key, user=other, db=db)
    assert first['id'] != second['id']
    assert db.scalar(select(func.count()).select_from(UploadReceipt)) == 2


def test_lifecycle_failure_rolls_back_file_audit_and_receipt(uploads, monkeypatch):
    db, _, _, upload, root = uploads
    def fail(*a, **kw): raise RuntimeError('outbox unavailable')
    monkeypatch.setattr('app.firm_module_runtime.process_document_uploaded', fail)
    with pytest.raises(RuntimeError): upload(uuid.uuid4())
    db.rollback()
    assert db.scalar(select(func.count()).select_from(File)) == 0
    assert db.scalar(select(func.count()).select_from(UploadReceipt)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'case.file.upload')) == 0
    assert not [p for p in root.rglob('*') if p.is_file()]


def test_msg_conversion_write_failure_leaves_no_partial_result(uploads, monkeypatch):
    db, _, _, upload, root = uploads
    monkeypatch.setattr('app.outlook_msg.outlook_msg_path_to_eml_bytes', lambda path: b'From: a@example.com\r\n\r\nmail')
    original = file_storage.os.replace
    def fail(source, destination):
        if str(destination).endswith('.eml'): raise OSError('storage full during conversion')
        return original(source, destination)
    monkeypatch.setattr(file_storage.os, 'replace', fail)
    key = uuid.uuid4()
    with pytest.raises(OSError): upload(key, body=b'synthetic msg', name='message.msg')
    db.rollback()
    assert not [p for p in root.rglob('*') if p.is_file()]
    assert db.scalar(select(func.count()).select_from(UploadReceipt)) == 0
    monkeypatch.setattr(file_storage.os, 'replace', original)
    result=upload(key, body=b'synthetic msg', name='message.msg')
    assert result['original_filename']=='message.eml'
    assert upload(key, body=b'synthetic msg', name='message.msg') == result
