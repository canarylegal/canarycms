"""Document safety regressions: real transactions and synthetic HTTP streams."""
import asyncio
import io
import uuid
from types import SimpleNamespace
import pytest
import httpx
from fastapi import UploadFile, HTTPException
from starlette.datastructures import Headers
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import File, FileCategory, FirmSettings, DocumentRecovery, AuditEvent, Precedent, PrecedentKind
from app import file_storage
from tests.ledger_test_helpers import add_user, add_case

@pytest.fixture
def db():
    with SessionLocal() as session:
        if session.bind.dialect.name != 'postgresql': pytest.skip('Requires isolated migrated PostgreSQL')
        yield session
        session.rollback()


def asset(db, root, column, category):
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test')
    path=root/(uuid.uuid4().hex+'.bin');path.write_bytes(b'synthetic existing asset')
    row=File(id=uuid.uuid4(),owner_id=user.id,category=category,storage_path=path.name,
        original_filename=path.name,mime_type='application/octet-stream',folder_path='',version=1,size_bytes=24)
    db.add(row);db.flush()
    settings=db.get(FirmSettings,1);setattr(settings,column,row.id);db.commit()
    return user,row.id,path

@pytest.mark.parametrize('helper,column,category',[
 ('_delete_letterhead_file','letterhead_file_id',FileCategory.firm_letterhead),
 ('_delete_quote_letterhead_file','quote_letterhead_file_id',FileCategory.firm_letterhead),
 ('_delete_portal_logo_file','portal_logo_file_id',FileCategory.firm_portal_logo),
 ('_delete_portal_background_file','portal_background_file_id',FileCategory.firm_portal_background),
 ('_delete_default_signature_file','default_signature_file_id',FileCategory.firm_default_signature),
])
def test_asset_rollback_restores_pointer_and_bytes(db,tmp_path,monkeypatch,helper,column,category):
    from app.routers import admin_firm_settings as service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    _,fid,path=asset(db,tmp_path,column,category)
    getattr(service,helper)(db,db.get(FirmSettings,1))
    db.rollback()
    with SessionLocal() as reader:
        assert getattr(reader.get(FirmSettings,1),column)==fid
        assert reader.get(File,fid) is not None
        assert path.exists()


def test_rejected_logo_replacement_preserves_existing_logo(db,tmp_path,monkeypatch):
    from app.routers import admin_firm_settings as service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user,fid,path=asset(db,tmp_path,'portal_logo_file_id',FileCategory.firm_portal_logo)
    monkeypatch.setattr(service,'_PORTAL_LOGO_MAX_BYTES',8)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.upload_portal_logo(upload=UploadFile(io.BytesIO(b'x'*9),filename='new.png',headers=Headers({'content-type':'image/png'})),admin=user,db=db))
    assert error.value.status_code==400
    db.rollback()
    assert db.get(FirmSettings,1).portal_logo_file_id==fid and db.get(File,fid) is not None
    assert path.exists()


@pytest.mark.parametrize('folder',['','letters'])
def test_delete_audit_failure_transaction_boundary(db,tmp_path,monkeypatch,folder):
    from app import case_file_mutate_service as service,case_folder_service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path)
    monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');case=add_case(db,fee_earner_user_id=user.id)
    path=tmp_path/'old.txt';path.write_bytes(b'original')
    fid=uuid.uuid4();row=File(id=fid,owner_id=user.id,case_id=case.id,category=FileCategory.case_document,
        storage_path='old.txt',original_filename='old.txt',mime_type='text/plain',folder_path=folder,version=1,size_bytes=8)
    db.add(row);db.commit();cid=case.id
    def fail_audit(*a,**kw):raise RuntimeError('synthetic audit write failure')
    monkeypatch.setattr(service,'log_event',fail_audit)
    with pytest.raises(RuntimeError):service.delete_case_file(cid,fid,user,db)
    db.rollback()
    with SessionLocal() as reader:
        remaining=reader.get(File,fid)
        assert remaining is not None
        if folder:
            assert reader.scalar(select(func.count()).select_from(DocumentRecovery).where(DocumentRecovery.file_id==fid))==0
            assert reader.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id==str(fid),AuditEvent.action=='case.file.delete'))==0
    assert path.read_bytes()==b'original'


@pytest.mark.parametrize('mode',['persist','print','callback'])
def test_onlyoffice_download_stops_at_budget(monkeypatch,mode):
    from app.routers import onlyoffice as service
    count=[]
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(20):
                count.append(1);yield b'xxxx'
    original=httpx.AsyncClient
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(200,stream=Body())),**kw))
    monkeypatch.setattr(service,'_internal_fetch_url_from_browser',lambda url:'https://synthetic.test/document')
    monkeypatch.setattr(service,'_OO_PERSIST_MAX_BYTES',8);monkeypatch.setattr(service,'_PRINT_STAGING_MAX_BYTES',8)
    if mode=='callback':
        assert asyncio.run(service._download_oo_document_bytes('https://synthetic.test/document',max_bytes=8)) is None
        assert len(count)==3
    else:
        with pytest.raises(HTTPException) as error:
            if mode=='persist':asyncio.run(service._fetch_onlyoffice_download_bytes('synthetic',log_label='audit'))
            else:asyncio.run(service.onlyoffice_print_stage(service.PrintStageIn(browser_url='https://synthetic.test/document'),SimpleNamespace(id=uuid.uuid4())))
        assert error.value.status_code==413 and len(count)==3


def upload_precedent(db,user,reference,data,key=None):
    from app.routers import precedents as service
    return service.upload_precedent(upload=UploadFile(io.BytesIO(data),filename='audit.txt',headers=Headers({'content-type':'text/plain'})),
        name='Synthetic',reference=reference,kind=PrecedentKind.document,matter_head_type_id=service.GLOBAL_SCOPE,
        matter_sub_type_id=service.GLOBAL_SCOPE,category_id=service.GLOBAL_SCOPE,admin=user,db=db,idempotency_key=key)


def test_precedent_enforces_shared_upload_limit(db,tmp_path,monkeypatch):
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setenv('CANARY_UPLOAD_MAX_BYTES','4')
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test')
    with pytest.raises(HTTPException) as error:
        upload_precedent(db,user,'AUDIT'+uuid.uuid4().hex[:12],b'12345678')
    assert error.value.status_code == 413
    assert not [p for p in tmp_path.rglob('*') if p.is_file()]


def test_precedent_lost_ack_retry_returns_original_without_orphan(db,tmp_path,monkeypatch):
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');reference='AUDIT'+uuid.uuid4().hex[:12];key=uuid.uuid4()
    commit=db.commit
    def lost_ack():commit();raise ConnectionError('synthetic lost commit ack')
    monkeypatch.setattr(db,'commit',lost_ack)
    with pytest.raises(ConnectionError):upload_precedent(db,user,reference,b'original',key)
    monkeypatch.setattr(db,'commit',commit);db.rollback()
    replay=upload_precedent(db,user,reference,b'original',key)
    assert replay.reference==reference
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Precedent).where(Precedent.reference==reference))==1
    files=[p for p in tmp_path.rglob('*') if p.is_file()]
    assert len(files)==1 and all(p.read_bytes()==b'original' for p in files)


def test_user_signature_rollback_preserves_bytes(db,tmp_path,monkeypatch):
    from app.routers import users
    from app.models import User
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(users,'FILES_ROOT',tmp_path)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test')
    path=tmp_path/'signature.png';path.write_bytes(b'synthetic signature')
    fid=uuid.uuid4();row=File(id=fid,owner_id=user.id,category=FileCategory.user_signature,
        storage_path=path.name,original_filename=path.name,mime_type='image/png',folder_path='',version=1,size_bytes=19)
    db.add(row);db.flush();user.signature_file_id=fid;db.commit();uid=user.id
    users._delete_user_signature_file(db,user);db.rollback()
    with SessionLocal() as reader:
        assert reader.get(User,uid).signature_file_id==fid and reader.get(File,fid) is not None
    assert path.exists()


def test_staff_upload_has_file_durability_barrier(db,tmp_path,monkeypatch):
    import os
    from app import file_upload_service as service
    from app.document_durability import create_document_bytes
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    monkeypatch.setattr('app.firm_module_runtime.process_document_uploaded',lambda *a,**kw:None)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');case=add_case(db,fee_earner_user_id=user.id)
    calls=[];original=os.fsync
    def spy(fd):calls.append(fd);return original(fd)
    monkeypatch.setattr(os,'fsync',spy)
    result=service.upload_case_file(case.id,UploadFile(io.BytesIO(b'synthetic'),filename='uploaded.txt',headers=Headers({'content-type':'text/plain'})),idempotency_key=uuid.uuid4(),user=user,db=db)
    assert calls
    with SessionLocal() as reader:assert reader.get(File,uuid.UUID(result['id'])) is not None
    create_document_bytes(b'control',root=tmp_path,file_id=uuid.uuid4(),filename='control.txt')
    assert calls


def test_asset_replacement_lost_ack_keeps_new_and_recoverable_old(db,tmp_path,monkeypatch):
    from app.routers import admin_firm_settings as service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user,old_id,path=asset(db,tmp_path,'portal_logo_file_id',FileCategory.firm_portal_logo)
    commit=db.commit
    def lost_ack():commit();raise ConnectionError('synthetic lost ACK')
    monkeypatch.setattr(db,'commit',lost_ack)
    with pytest.raises(ConnectionError):
        asyncio.run(service.upload_portal_logo(upload=UploadFile(io.BytesIO(b'new synthetic png'),filename='new.png',headers=Headers({'content-type':'image/png'})),admin=user,db=db))
    with SessionLocal() as reader:
        current=reader.get(File,reader.get(FirmSettings,1).portal_logo_file_id)
        assert current.id!=old_id and (tmp_path/current.storage_path).read_bytes()==b'new synthetic png'
        recovery=reader.scalar(select(DocumentRecovery).where(DocumentRecovery.file_id==old_id))
        assert (tmp_path/recovery.storage_path).read_bytes()==b'synthetic existing asset'
    assert path.read_bytes()==b'synthetic existing asset'


def test_stale_asset_owner_retires_current_pointer(db,tmp_path,monkeypatch):
    from app.routers import admin_firm_settings as service
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user,old_id,path=asset(db,tmp_path,'portal_logo_file_id',FileCategory.firm_portal_logo)
    stale=db.get(FirmSettings,1)
    replacement_id=uuid.uuid4();replacement=tmp_path/'replacement.png';replacement.write_bytes(b'replacement')
    with SessionLocal() as other:
        settings=other.get(FirmSettings,1)
        service._delete_portal_logo_file(other,settings)
        other.add(File(id=replacement_id,owner_id=user.id,category=FileCategory.firm_portal_logo,
            storage_path=replacement.name,original_filename=replacement.name,mime_type='image/png',folder_path='',version=1,size_bytes=11))
        other.flush();settings.portal_logo_file_id=replacement_id;other.commit()
    service._delete_portal_logo_file(db,stale);db.commit()
    with SessionLocal() as reader:
        assert reader.get(FirmSettings,1).portal_logo_file_id is None
        assert reader.get(File,replacement_id) is None
        assert reader.scalar(select(func.count()).select_from(DocumentRecovery).where(DocumentRecovery.file_id.in_([old_id,replacement_id])))==2
    assert path.exists() and replacement.exists()


def test_upload_fsync_failure_cannot_publish_file_or_receipt(db,tmp_path,monkeypatch):
    import os
    from app import file_upload_service as service
    from app.models import UploadReceipt
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path);monkeypatch.setattr(service,'FILES_ROOT',tmp_path)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');case=add_case(db,fee_earner_user_id=user.id)
    cid=case.id
    def fail(fd):raise OSError('synthetic disk flush failure')
    monkeypatch.setattr(os,'fsync',fail)
    with pytest.raises(OSError):service.upload_case_file(cid,UploadFile(io.BytesIO(b'content'),filename='sample.txt'),idempotency_key=uuid.uuid4(),user=user,db=db)
    db.rollback()
    with SessionLocal() as reader:assert reader.scalar(select(func.count()).select_from(File).where(File.case_id==cid))==0
    assert not [p for p in tmp_path.rglob('*') if p.is_file()]


@pytest.mark.parametrize('phase',['headers','body'])
def test_onlyoffice_total_deadline_closes_stream(monkeypatch,phase):
    from app.routers import onlyoffice as service
    closed=[]
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                yield b'x';await asyncio.sleep(.01)
        async def aclose(self):closed.append(True)
    async def respond(request):
        if phase=='headers':await asyncio.sleep(1)
        return httpx.Response(200,stream=SlowBody())
    original=httpx.AsyncClient
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    monkeypatch.setattr(service,'_OO_DOWNLOAD_TIMEOUT',.05)
    import time
    started=time.monotonic()
    with pytest.raises(HTTPException) as error:asyncio.run(service._fetch_oo_bytes('https://synthetic.test/',max_bytes=1000))
    assert error.value.status_code==502 and time.monotonic()-started<.5
    if phase=='body':assert closed==[True]


def test_onlyoffice_valid_boundary_and_redirect_refusal(monkeypatch):
    from app.routers import onlyoffice as service
    original=httpx.AsyncClient;calls=[]
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(302,headers={'Location':'https://untrusted.test/'}) if request.url.path=='/redirect' else httpx.Response(200,content=b'12345678')
    def client(**kw):
        assert not kw['trust_env'] and not kw['follow_redirects']
        return original(transport=httpx.MockTransport(respond),**kw)
    monkeypatch.setattr(service.httpx,'AsyncClient',client)
    assert asyncio.run(service._fetch_oo_bytes('https://synthetic.test/ok',max_bytes=8))==b'12345678'
    with pytest.raises(HTTPException) as error:asyncio.run(service._fetch_oo_bytes('https://synthetic.test/redirect',max_bytes=8))
    assert error.value.status_code==502 and calls==['/ok','/redirect']


def test_precedent_retry_rejects_changes_and_deleted_record(db,tmp_path,monkeypatch):
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');reference='AUDIT'+uuid.uuid4().hex[:12];key=uuid.uuid4()
    result=upload_precedent(db,user,reference,b'original',key)
    with pytest.raises(HTTPException) as error:upload_precedent(db,user,reference,b'changed',key)
    assert error.value.status_code==409;db.rollback()
    db.delete(db.get(Precedent,result.id));db.commit()
    with pytest.raises(HTTPException) as error:upload_precedent(db,user,reference,b'original',key)
    assert error.value.status_code==410
    assert len([p for p in tmp_path.rglob('*') if p.is_file()])==1


def test_precedent_concurrent_retry_creates_once(db,tmp_path,monkeypatch):
    from app.routers import precedents
    from app.models import User
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    monkeypatch.setattr(file_storage,'FILES_ROOT',tmp_path)
    user=add_user(db,email='audit-'+uuid.uuid4().hex+'@example.test');uid=user.id
    reference='AUDIT'+uuid.uuid4().hex[:12];key=uuid.uuid4();entered,release=Event(),Event()
    original=precedents.stream_upload_to_path
    def held(*a,**kw):entered.set();assert release.wait(5);return original(*a,**kw)
    monkeypatch.setattr(precedents,'stream_upload_to_path',held)
    def upload():
        with SessionLocal() as session:return upload_precedent(session,session.get(User,uid),reference,b'original',key)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first=pool.submit(upload)
        try:
            assert entered.wait(5)
            with pytest.raises(HTTPException) as error:upload()
            assert error.value.status_code==429
        finally:release.set()
        saved=first.result(5)
    assert upload().id==saved.id
    assert len([p for p in tmp_path.rglob('*') if p.is_file()])==1
