"""A stale editor must not silently replace an accepted edit or its audit history."""
import uuid
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from app.models import File, FileCategory, DocumentRecovery, AuditEvent
from app.schemas import CommentFileUpdate
from app import file_storage, case_file_mutate_service as service
from tests.test_core_audit_regressions import audit_db, add_user, add_case


def test_stale_comment_preserves_current_bytes_version_and_history(audit_db, tmp_path, monkeypatch):
    db = audit_db
    user = add_user(db, email=uuid.uuid4().hex+'@example.test')
    case = add_case(db, fee_earner_user_id=user.id)
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr(service, 'FILES_ROOT', tmp_path)
    (tmp_path/'note.txt').write_text('original')
    row = File(id=uuid.uuid4(), case_id=case.id, owner_id=user.id, category=FileCategory.case_document,
        storage_path='note.txt', original_filename='note.txt', folder_path='', mime_type='text/plain', size_bytes=8, version=1)
    db.add(row); db.commit()
    service.update_comment_file(case.id,row.id,CommentFileUpdate(text='first edit',expected_version=1),user,db)
    current_path = row.storage_path
    before_audit = db.scalar(select(func.count()).select_from(AuditEvent))
    with pytest.raises(HTTPException) as exc:
        service.update_comment_file(case.id,row.id,CommentFileUpdate(text='stale edit',expected_version=1),user,db)
    assert exc.value.status_code == 409
    db.rollback(); db.refresh(row)
    assert row.version == 2 and row.storage_path == current_path
    assert (tmp_path/current_path).read_text() == 'first edit'
    assert db.scalar(select(func.count()).select_from(DocumentRecovery)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == before_audit
    service.update_comment_file(case.id,row.id,CommentFileUpdate(text='combined edit',expected_version=2),user,db)
    assert row.version == 3
    assert (tmp_path/row.storage_path).read_text() == 'combined edit'


@pytest.mark.parametrize('version',[None,0,-1,True,'1'])
def test_comment_requires_an_explicit_integer_version(version):
    with pytest.raises(ValidationError):
        CommentFileUpdate.model_validate({'text':'draft', **({'expected_version':version} if version is not None else {})})


def test_comment_read_returns_matching_revision_and_bounds_large_text(audit_db,tmp_path,monkeypatch):
    import json
    from app.routers import files
    db=audit_db
    user=add_user(db,email=uuid.uuid4().hex+'@example.test')
    case=add_case(db,fee_earner_user_id=user.id)
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path)
    monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    path=tmp_path/'read.txt';path.write_text('original')
    row=File(id=uuid.uuid4(),case_id=case.id,owner_id=user.id,category=FileCategory.case_document,
        storage_path=path.name,original_filename=path.name,folder_path='',mime_type='text/plain',size_bytes=8,version=1)
    db.add(row);db.commit()
    response=files.read_comment_file(case.id,row.id,user,db)
    assert json.loads(response.body)=={'text':'original','version':1}
    assert response.headers['cache-control']=='no-store'
    service.update_comment_file(case.id,row.id,CommentFileUpdate(text='new bytes',expected_version=1),user,db)
    assert json.loads(files.read_comment_file(case.id,row.id,user,db).body)=={'text':'new bytes','version':2}
    # Guard is based on actual bytes, even if legacy metadata understates size.
    (tmp_path/row.storage_path).write_bytes(b'x'*2_000_001)
    with pytest.raises(HTTPException) as exc:files.read_comment_file(case.id,row.id,user,db)
    assert exc.value.status_code==413
