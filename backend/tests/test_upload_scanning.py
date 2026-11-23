"""Synthetic scanning boundaries. No external scanner/provider is contacted."""
import io
import socket
import struct
import threading
import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import File, User, ContactPortalGrant
from app import upload_scanning as scans
from tests.test_permission_boundaries_postgres import sample, allow_staff

@pytest.fixture
def enabled(monkeypatch, tmp_path):
    monkeypatch.setenv('CANARY_UPLOAD_SCAN_MODE', 'required')
    monkeypatch.setenv('CANARY_QUARANTINE_ROOT', str(tmp_path/'quarantine'))
    monkeypatch.setattr(scans, 'scan_stream', lambda stream: None)
    monkeypatch.setattr(scans, 'scanner_version', lambda: 'synthetic-engine')
    yield
    # Don't let unfinished synthetic entries leak into subsequent tests.
    with SessionLocal() as db:
        for row in db.scalars(select(File).where(File.scan_state.in_(['pending','error']))):
            row.scan_state='blocked'
        db.commit()


def upload(c, sample, name='example.pdf', raw=b'%PDF synthetic', **kwargs):
    return c.post('/cases/'+sample['case']+'/files', headers=sample['admin_headers'],
                  files={'upload': (name, raw, 'application/octet-stream')}, **kwargs)


def run_scan():
    with SessionLocal() as db:
        assert scans.scan_one(db)


def state(identity):
    with SessionLocal() as db:
        return db.get(File, uuid.UUID(identity)).scan_state


def test_pending_visible_but_no_content_or_edit_and_policy_disable_cannot_release(sample, enabled, monkeypatch):
    with TestClient(app) as c:
        r=upload(c,sample); assert r.status_code==201,r.text
        identity=r.json()['id'];assert r.json()['scan_state']=='pending'
        base=f"/cases/{sample['case']}/files/{identity}"
        rows=c.get(f"/cases/{sample['case']}/files",headers=sample['admin_headers']).json()
        assert next(f for f in rows if f['id']==identity)['scan_state']=='pending'
        for suffix in ['']:
            # Check the actual download endpoint, not only the ORM guard.
            response=c.get(base+suffix,headers=sample['admin_headers'])
            assert response.status_code == 423,response.text
        with SessionLocal() as db:
            row=db.get(File,uuid.UUID(identity))
            with pytest.raises(HTTPException) as error: _=row.storage_path
            assert error.value.status_code==423
            from app.file_storage import FILES_ROOT
            assert not (FILES_ROOT/row._storage_path).exists()
        monkeypatch.setenv('CANARY_UPLOAD_SCAN_MODE','disabled')
        with SessionLocal() as db:
            assert not scans.scan_one(db)
            with pytest.raises(HTTPException): _=db.get(File,uuid.UUID(identity)).storage_path


def test_clean_release_exact_bytes_and_mail_identity(sample,enabled):
    raw=b'From: sender@example.com\r\nMessage-ID: <scan@example.com>\r\n\r\nSynthetic email'
    with TestClient(app) as c:
        r=upload(c,sample,'example.eml',raw);identity=r.json()['id']
    run_scan()
    with SessionLocal() as db:
        row=db.get(File,uuid.UUID(identity));assert row.scan_state=='clean',row.scan_error
        from app.file_storage import FILES_ROOT
        assert (FILES_ROOT/row.storage_path).read_bytes()==raw
        assert row.source_internet_message_id=='<scan@example.com>'
        assert row.scan_quarantine_key is None


@pytest.mark.parametrize('error,expected',[(scans.Detected('scanner_detection'),'blocked'),(scans.ScanFailure('timeout'),'error'),(OSError('secret internal detail'),'error')])
def test_detection_failure_and_timeout_do_not_release(sample,enabled,monkeypatch,error,expected):
    def fail(stream): raise error
    monkeypatch.setattr(scans,'scan_stream',fail)
    with TestClient(app) as c:
        r=upload(c,sample);identity=r.json()['id']
    run_scan();assert state(identity)==expected
    with SessionLocal() as db:
        row=db.get(File,uuid.UUID(identity));assert row.scan_error != 'secret internal detail'
        assert (scans.quarantine_root()/row.scan_quarantine_key).exists()
        with pytest.raises(HTTPException): _=row.storage_path


def test_replaced_quarantine_bytes_never_released(sample,enabled):
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    with SessionLocal() as db:
        row=db.get(File,uuid.UUID(identity));(scans.quarantine_root()/row.scan_quarantine_key).write_bytes(b'changed')
    run_scan();assert state(identity)=='blocked'


def test_revoked_uploader_cannot_release(sample,enabled):
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    with SessionLocal() as db:
        db.get(User,uuid.UUID(sample['admin'])).is_active=False;db.commit()
    run_scan();assert state(identity)=='blocked'


def test_pending_idempotent_retry_and_clean_receipt(sample,enabled):
    key=str(uuid.uuid4());headers=dict(sample['admin_headers'],**{'Idempotency-Key':key})
    with TestClient(app) as c:
        def send():return c.post(f"/cases/{sample['case']}/files",headers=headers,files={'upload':('repeat.txt',b'hello','text/plain')})
        first=send();second=send();assert first.status_code==second.status_code==201
        assert first.json()==second.json()
        run_scan();third=send();assert third.json()['id']==first.json()['id'];assert third.json()['scan_state']=='clean'


def test_worker_claim_skip_locked(sample,enabled):
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    with SessionLocal() as locked:
        locked.scalar(select(File).where(File.id==uuid.UUID(identity)).with_for_update())
        with SessionLocal() as other:assert scans.scan_one(other) is False
    run_scan();assert state(identity)=='clean'


def test_post_scan_bytes_changed_during_publication_blocked(sample,enabled,monkeypatch):
    original=scans.shutil.copyfile
    def changed(source,dest):
        Path(source).write_bytes(b'changed-after-scan');return original(source,dest)
    monkeypatch.setattr(scans.shutil,'copyfile',changed)
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    run_scan();assert state(identity)=='blocked'


def test_admin_retry_requires_admin_and_never_releases_without_scan(sample,enabled,monkeypatch):
    with TestClient(app) as c:
        identity=upload(c,sample).json()['id']
        with SessionLocal() as db:
            row=db.get(File,uuid.UUID(identity));row.scan_state='error';row.scan_attempts=3;db.commit()
        url='/admin/storage/upload-scanning/'+identity+'/retry'
        assert c.post(url,headers=sample['headers']).status_code==403
        assert c.post(url,headers=sample['admin_headers']).status_code==200
        assert state(identity)=='pending'
        assert c.get('/admin/storage/upload-scanning',headers=sample['headers']).status_code==403


@pytest.mark.parametrize('response,expected',[(b'stream: OK\0',None),(b'stream: Eicar FOUND\0',scans.Detected),
    (b'stream: Heuristics.Limits.Exceeded FOUND\0',scans.Detected),(b'INSTREAM size limit exceeded. ERROR\0',scans.ScanFailure),
    (b'stream: OK',scans.ScanFailure),(b'OK\0',scans.ScanFailure)])
def test_real_socket_protocol(monkeypatch,response,expected):
    monkeypatch.setattr(scans, "scanner_version", lambda: "synthetic-engine")
    with socket.socket() as server:
        server.bind(('127.0.0.1',0));server.listen(1)
        monkeypatch.setenv('CANARY_CLAMAV_HOST','127.0.0.1');monkeypatch.setenv('CANARY_CLAMAV_PORT',str(server.getsockname()[1]))
        def serve():
            with server.accept()[0] as peer:
                def read(n):
                    result=b''
                    while len(result)<n:result+=peer.recv(n-len(result))
                    return result
                assert read(10)==b'zINSTREAM\0'
                while size:=struct.unpack('!I',read(4))[0]:read(size)
                peer.sendall(response)
        thread=threading.Thread(target=serve);thread.start()
        if expected:
            with pytest.raises(expected):scans.scan_stream(io.BytesIO(b'synthetic'))
        else:scans.scan_stream(io.BytesIO(b'synthetic'))
        thread.join(timeout=2);assert not thread.is_alive()


def test_invalid_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv('CANARY_UPLOAD_SCAN_MODE','typo')
    with pytest.raises(RuntimeError):scans.validate_config()


@pytest.mark.parametrize('revoke', [False, True])
def test_portal_upload_remains_visible_and_revoked_grant_blocks_release(sample,enabled,revoke):
    from app.security import create_portal_session_token
    with SessionLocal() as db:
        db.get(ContactPortalGrant,uuid.UUID(sample['grant'])).can_upload=True;db.commit()
    from app.models import ContactPortalAccess
    with SessionLocal() as db:
        version=db.scalar(select(ContactPortalAccess).where(ContactPortalAccess.contact_id==uuid.UUID(sample['contact']))).session_version
    headers={'Authorization':'Bearer '+create_portal_session_token(contact_id=sample['contact'],session_version=version)}
    base='/portal/grants/'+sample['grant']+'/files'
    with TestClient(app) as c:
        r=c.post(base,headers=headers,files={'upload':('portal.pdf',b'%PDF synthetic','application/pdf')})
        assert r.status_code==201,r.text
        identity=r.json()['id'];assert r.json()['scan_state']=='pending'
        assert c.get(base+'/'+identity,headers=headers).status_code==423
        if revoke:
            with SessionLocal() as db:
                db.get(ContactPortalGrant,uuid.UUID(sample['grant'])).can_upload=False;db.commit()
        run_scan();assert state(identity)==('blocked' if revoke else 'clean')
        if not revoke:assert c.get(base+'/'+identity,headers=headers).status_code==200


def test_pending_checkout_and_export_cannot_access(sample,enabled,monkeypatch):
    monkeypatch.setenv('ONLYOFFICE_JWT_SECRET','synthetic-secret')
    monkeypatch.setenv('ONLYOFFICE_DS_PUBLIC_URL','http://synthetic-onlyoffice')
    with TestClient(app) as c:
        identity=upload(c,sample,'example.docx',b'synthetic docx').json()['id']
        base=f"/cases/{sample['case']}/files/{identity}"
        assert c.post(base+'/checkout-edit',headers=sample['admin_headers']).status_code==423
        assert c.get(base+'/onlyoffice-config',headers=sample['admin_headers']).status_code==423


def test_scanner_rejects_replacement_without_changing_current_bytes(sample,enabled,monkeypatch):
    from app.document_durability import stage_document_bytes
    from app.file_storage import FILES_ROOT
    def fail(stream):raise scans.Detected('scanner_detection')
    monkeypatch.setattr(scans,'scan_stream',fail)
    with SessionLocal() as db:
        row=db.get(File,uuid.UUID(sample['file']));old_path=row.storage_path;old_bytes=(FILES_ROOT/old_path).read_bytes()
        with pytest.raises(HTTPException) as error:stage_document_bytes(db,row,b'malware',root=FILES_ROOT)
        assert error.value.status_code==422
        assert row.storage_path==old_path and (FILES_ROOT/old_path).read_bytes()==old_bytes


def test_promotion_failure_keeps_retriable_quarantine_reference(sample,enabled,monkeypatch):
    import app.firm_module_runtime as runtime
    def fail(*a,**kw):raise RuntimeError('synthetic hook failure')
    monkeypatch.setattr(runtime,'process_document_uploaded',fail)
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    run_scan()
    with SessionLocal() as db:
        row=db.get(File,uuid.UUID(identity));assert row.scan_state=='error'
        assert row.scan_quarantine_key and (scans.quarantine_root()/row.scan_quarantine_key).exists()
        with pytest.raises(HTTPException):_=row.storage_path


def test_lost_commit_does_not_destroy_quarantined_bytes(sample,enabled,monkeypatch):
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    with SessionLocal() as db:
        def fail():raise RuntimeError('synthetic lost acknowledgement')
        monkeypatch.setattr(db,'commit',fail)
        with pytest.raises(RuntimeError):scans.scan_one(db)
        db.rollback()
    assert state(identity)=='pending'
    run_scan();assert state(identity)=='clean'


def test_archive_limits_checked_even_if_scanner_returns_ok():
    import zipfile
    packed=io.BytesIO()
    with zipfile.ZipFile(packed,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('oversize.txt',b'x'*1025)
    with pytest.raises(scans.Detected):scans.validate_zip_limits(packed,1024)


def test_quarantine_quota_rejects_without_publishing(sample,enabled,monkeypatch):
    monkeypatch.setenv('CANARY_QUARANTINE_MAX_BYTES','2')
    with TestClient(app) as c:
        result=upload(c,sample);assert result.status_code==507
    assert not [p for p in scans.quarantine_root().iterdir() if not p.name.startswith('.')]


def test_admin_can_discard_blocked_upload_without_exposing_bytes(sample,enabled):
    with TestClient(app) as c:
        identity=upload(c,sample).json()['id']
        with SessionLocal() as db:
            key=db.get(File,uuid.UUID(identity)).scan_quarantine_key
        route='/admin/storage/upload-scanning/'+identity
        assert c.delete(route,headers=sample['headers']).status_code==403
        assert c.delete(route,headers=sample['admin_headers']).status_code==204
        assert not (scans.quarantine_root()/key).exists()
        with SessionLocal() as db:assert db.get(File,uuid.UUID(identity)) is None


def test_recovery_inventory_checks_private_quarantine(sample,enabled):
    from app.recovery_integrity import audit
    from app.file_storage import FILES_ROOT
    with TestClient(app) as c:identity=upload(c,sample).json()['id']
    with SessionLocal() as db:
        result=audit(db.connection(),FILES_ROOT)
        assert result['quarantine']['checked']>=1
        missing_before=result['quarantine']['missing']
        row=db.get(File,uuid.UUID(identity));(scans.quarantine_root()/row.scan_quarantine_key).unlink()
        result=audit(db.connection(),FILES_ROOT)
        assert result['quarantine']['missing']==missing_before+1 and result['ok'] is False


def test_pending_file_cannot_enter_exports_or_email_handoffs(sample,enabled):
    with TestClient(app) as c:
        identity=upload(c,sample).json()['id'];base=f"/cases/{sample['case']}/files"
        assert c.get(base+'/export-zip',headers=sample['admin_headers']).status_code==423
        r=c.post(base+'/email-compose-handoff',headers=sample['admin_headers'],json={'attachment_file_ids':[identity]})
        assert r.status_code==423,r.text


@pytest.mark.parametrize('days,accepted',[(0,True),(10,False)])
def test_signature_age_is_enforced(monkeypatch,days,accepted):
    from datetime import datetime,timezone,timedelta
    stamp=(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%a %b %d %H:%M:%S %Y')
    class Peer:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def sendall(self,command):assert command==b'zVERSION\0'
        def recv(self,size):return ('ClamAV 1.4.7/12345/'+stamp+'\0').encode()
    monkeypatch.setattr(scans.socket,'create_connection',lambda *a,**kw:Peer())
    if accepted:assert scans.scanner_version().startswith('ClamAV ')
    else:
        with pytest.raises(scans.ScanFailure,match='stale'):scans.scanner_version()


def test_msg_conversion_is_scanned_before_publication(sample,enabled,monkeypatch):
    from app import outlook_msg
    monkeypatch.setattr(outlook_msg,'outlook_msg_path_to_eml_bytes',lambda path:b'converted synthetic mail')
    def scanner(stream):
        if b'converted' in stream.read():raise scans.Detected('scanner_detection')
    monkeypatch.setattr(scans,'scan_stream',scanner)
    with TestClient(app) as c:identity=upload(c,sample,'example.msg',b'original synthetic msg').json()['id']
    run_scan();assert state(identity)=='blocked'
    with SessionLocal() as db:
        row=db.get(File,uuid.UUID(identity));assert row.original_filename=='example.msg' and row.scan_quarantine_key
