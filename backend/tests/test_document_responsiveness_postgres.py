"""Exercise the actual save route against a contended PostgreSQL document row."""
import asyncio
import threading
import time
import uuid
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from app.db import get_db, SessionLocal, engine
from app.deps import get_current_user
from app.models import UserRole
from app.routers import files
from tests.test_core_audit_regressions import audit_db, add_user, add_case
from tests.test_cl18_release_edit_save import _file, _open_session


@pytest.mark.asyncio
async def test_save_arm_waits_without_stalling_unrelated_requests(audit_db):
    db=audit_db
    user=add_user(db,email=uuid.uuid4().hex+'@example.test')
    user.role=UserRole.admin;db.commit()
    case=add_case(db,fee_earner_user_id=user.id)
    row=_file(db,case,user)
    session=_open_session(db,case,row,user)
    session.document_key='contention-regression';db.commit()
    case_id,file_id=case.id,row.id
    db.refresh(user);db.expunge(user)
    app=FastAPI();app.include_router(files.router)
    def request_db():
        with SessionLocal() as request_session:
            yield request_session
    app.dependency_overrides[get_db]=request_db
    app.dependency_overrides[get_current_user]=lambda:user
    @app.get('/health')
    async def health():return {'ok':True}
    locked=threading.Event();release=threading.Event()
    def holder():
        with engine.begin() as connection:
            connection.execute(text('SELECT id FROM file WHERE id=:id FOR UPDATE'),{'id':file_id})
            locked.set();release.wait(3)
    thread=threading.Thread(target=holder);thread.start()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        pending=None
        try:
            async with asyncio.timeout(2):
                while not locked.is_set():await asyncio.sleep(.01)
            started=time.monotonic()
            pending=asyncio.create_task(client.post(f'/cases/{case_id}/files/{file_id}/oo-force-save',params={'phase':'arm','doc_key':'contention-regression'}))
            await asyncio.sleep(.1)
            response=await asyncio.wait_for(client.get('/health'),.5)
            assert response.status_code==200
            assert time.monotonic()-started<1
            assert not pending.done(), 'save should still be waiting for the held row lock'
        finally:
            release.set()
            await asyncio.to_thread(thread.join)
        response=await pending
        assert response.status_code==200
        assert response.json()['base_version']==1
