"""Wire contract and compatibility checks using only a disposable database."""
import asyncio
import io
import uuid
import pytest
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from sqlalchemy import select, func
from app.db import SessionLocal, get_db
from app import file_storage
from app.models import File, FileCategory, FirmSettings, Precedent, User
from tests.ledger_test_helpers import add_user
from tests.test_document_safety_regressions import db, asset


def test_precedent_header_recovers_lost_ack_over_http(db,tmp_path,monkeypatch):
    from app.routers import precedents
    from app.deps import require_admin
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path)
    actor=add_user(db,email='wire-'+uuid.uuid4().hex+'@example.test');uid=actor.id
    app=FastAPI();app.include_router(precedents.router)
    app.dependency_overrides[require_admin]=lambda:actor
    first=[True]
    def session():
        with SessionLocal() as current:
            commit=current.commit
            def uncertain():
                commit()
                if first[0]:first[0]=False;raise ConnectionError('synthetic lost ACK')
            current.commit=uncertain
            try:yield current
            except Exception:current.rollback();raise
    app.dependency_overrides[get_db]=session
    reference='WIRE'+uuid.uuid4().hex[:12]
    with TestClient(app,raise_server_exceptions=False) as client:
        data={'name':'Synthetic','reference':reference,'kind':'document'}
        key={'Idempotency-Key':str(uuid.uuid4())}
        def send(content=b'original'):return client.post('/precedents',headers=key,data=data,files={'upload':('wire.txt',content,'text/plain')})
        assert send().status_code==500
        response=send();assert response.status_code==201,response.text
        assert send().json()==response.json()
        assert send(b'changed').status_code==409
    with SessionLocal() as reader:
        assert reader.scalar(select(func.count()).select_from(Precedent).where(Precedent.reference==reference))==1
    assert len([p for p in tmp_path.rglob('*') if p.is_file()])==1


@pytest.mark.parametrize('kind',['letterhead','quote_letterhead'])
def test_invalid_letterhead_preserves_previous_asset(db,tmp_path,monkeypatch,kind):
    from app.routers import admin_firm_settings as service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user,fid,path=asset(db,tmp_path,kind+'_file_id',FileCategory.firm_letterhead)
    with pytest.raises(HTTPException) as error:
        asyncio.run(getattr(service,'upload_'+kind)(UploadFile(io.BytesIO(b'not a docx'),filename='bad.docx'),user,db))
    assert error.value.status_code==400;db.rollback()
    assert getattr(db.get(FirmSettings,1),kind+'_file_id')==fid and path.exists()


@pytest.mark.parametrize('kind',['letterhead','quote_letterhead'])
def test_valid_letterhead_replacement_retains_original(db,tmp_path,monkeypatch,kind):
    from docx import Document
    from app.routers import admin_firm_settings as service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user,fid,path=asset(db,tmp_path,kind+'_file_id',FileCategory.firm_letterhead)
    stream=io.BytesIO();document=Document();document.add_paragraph('Synthetic letterhead');document.save(stream)
    asyncio.run(getattr(service,'upload_'+kind)(UploadFile(io.BytesIO(stream.getvalue()),filename='good.docx'),user,db))
    replacement=db.get(File,getattr(db.get(FirmSettings,1),kind+'_file_id'))
    assert replacement.id!=fid and replacement.checksum
    assert (tmp_path/replacement.storage_path).read_bytes()==stream.getvalue()
    assert path.read_bytes()==b'synthetic existing asset'
