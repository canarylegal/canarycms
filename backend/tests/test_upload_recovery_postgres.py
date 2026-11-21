"""Real concurrent transactions; run only against the migrated disposable fixture."""
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import File, User
from app import file_upload_service as service
from tests.ledger_test_helpers import add_user, add_case


def test_concurrent_receipt_lock_and_retry(db, monkeypatch):
    if db.bind.dialect.name != 'postgresql': pytest.skip('PostgreSQL advisory locks')
    user=add_user(db); case=add_case(db,fee_earner_user_id=user.id)
    uid,cid=user.id,case.id
    started, release = Event(),Event()
    original=service.stream_upload_to_path
    def held(*args,**kwargs):
        started.set()
        assert release.wait(10)
        return original(*args,**kwargs)
    monkeypatch.setattr(service,'stream_upload_to_path',held)
    key=uuid.uuid4()
    def upload():
        with SessionLocal() as session:
            return service.upload_case_file(cid,UploadFile(io.BytesIO(b'concurrent'),filename='concurrent.txt'),
                idempotency_key=key,user=session.get(User,uid),db=session)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(upload)
        try:
            assert started.wait(10)
            with pytest.raises(HTTPException) as error: upload()
            assert error.value.status_code==429
        finally: release.set()
        result=first.result(10)
    assert upload()==result
    assert db.scalar(select(func.count()).select_from(File).where(File.case_id==cid))==1
