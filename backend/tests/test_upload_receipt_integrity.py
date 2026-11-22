import io
import uuid
import pytest
from fastapi import UploadFile, HTTPException
from starlette.datastructures import Headers
from app import file_storage,file_upload_service as service
from app.models import File
from tests.ledger_test_helpers import add_user,add_case
from tests.test_document_safety_regressions import db

@pytest.mark.parametrize('damage',['missing','changed'])
def test_upload_retry_rejects_unusable_or_changed_bytes(db,tmp_path,monkeypatch,damage):
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    monkeypatch.setattr('app.firm_module_runtime.process_document_uploaded',lambda *a,**kw:None)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');case=add_case(db,fee_earner_user_id=user.id)
    key=uuid.uuid4()
    def upload():return service.upload_case_file(case.id,UploadFile(io.BytesIO(b'original'),filename='audit.txt',headers=Headers({'content-type':'text/plain'})),idempotency_key=key,user=user,db=db)
    first=upload();row=db.get(File,uuid.UUID(first['id']));path=tmp_path/row.storage_path
    if damage=='missing':path.unlink()
    else:path.write_bytes(b'corrupted')
    with pytest.raises(HTTPException) as error:
        upload()
    assert error.value.status_code == 409
    assert row.checksum is not None


def test_retry_accepts_legitimate_later_version_and_refuses_legacy_unknown_checksum(db,tmp_path,monkeypatch):
    from app.document_durability import lock_document,stage_document_bytes
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    monkeypatch.setattr('app.firm_module_runtime.process_document_uploaded',lambda *a,**kw:None)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');case=add_case(db,fee_earner_user_id=user.id);key=uuid.uuid4()
    def upload():return service.upload_case_file(case.id,UploadFile(io.BytesIO(b'original'),filename='audit.txt'),idempotency_key=key,user=user,db=db)
    first=upload();row=lock_document(db,db.get(File,uuid.UUID(first['id'])))
    stage_document_bytes(db,row,b'legitimate new version',root=tmp_path);row.version=2;db.commit()
    assert upload()==first
    assert (tmp_path/row.storage_path).read_bytes()==b'legitimate new version'
    row.checksum=None;db.commit()
    with pytest.raises(HTTPException) as error:upload()
    assert error.value.status_code==409
