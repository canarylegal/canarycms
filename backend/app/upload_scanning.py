"""Optional upload scanning. Only this module can read quarantined bytes.

A pending File is a durable queue entry. File.storage_path denies content access
independently of the current deployment policy, including after scanning is disabled.
"""
from __future__ import annotations
import hashlib
import os
import shutil
import socket
import struct
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, text, or_

AVAILABLE = ('unscanned', 'clean')


def mode():
    value = os.getenv('CANARY_UPLOAD_SCAN_MODE', 'disabled').strip().lower()
    if value not in ('disabled', 'required'):
        raise RuntimeError('CANARY_UPLOAD_SCAN_MODE must be disabled or required')
    return value


def required():
    return mode() == 'required'


def positive_int(name, default):
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(name + ' must be positive')
    return value


def quarantine_root():
    from app.file_storage import FILES_ROOT
    root = Path(os.getenv('CANARY_QUARANTINE_ROOT', str(FILES_ROOT) + '.quarantine')).resolve()
    if root.is_relative_to(FILES_ROOT) or FILES_ROOT.is_relative_to(root):
        raise RuntimeError('Quarantine must be separate from document storage')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def validate_config():
    mode()
    if required():
        if os.getenv('CANARY_UPLOAD_SCAN_PROVIDER', 'clamav') != 'clamav':
            raise RuntimeError('Unsupported upload scanner')
        quarantine_root()
        positive_int('CANARY_CLAMAV_PORT', 3310)
        positive_int('CANARY_UPLOAD_SCAN_TIMEOUT_SECONDS', 30)
        positive_int('CANARY_CLAMAV_MAX_SIGNATURE_AGE_DAYS', 7)
        positive_int('CANARY_UPLOAD_SCAN_MAX_BYTES', 26214400)
        positive_int('CANARY_QUARANTINE_MAX_BYTES', 1073741824)
        if os.getenv('CANARY_UPLOAD_SCAN_WORKER_ENABLED', '0') not in ('0', '1'):
            raise RuntimeError('CANARY_UPLOAD_SCAN_WORKER_ENABLED must be 0 or 1')


def require_available(row):
    if (row.scan_state or 'unscanned') not in AVAILABLE:
        raise HTTPException(423, 'Document unavailable: security check ' + row.scan_state)


class ScanFailure(Exception):
    pass


class Detected(ScanFailure):
    pass


def validate_zip_limits(stream, limit):
    """ClamAV can skip oversized ZIP members without a limit alert. Check ZIP
    directories independently, including Office packages, before accepting OK.
    Never extract paths; bound member count, expanded bytes and nesting.
    """
    import io
    import zipfile
    position = stream.tell()
    budget = [100 * 1024 * 1024, 1000]
    def check(source, depth):
        source.seek(0)
        if source.read(4) not in (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'):
            return
        if depth > 8:
            raise Detected('archive_limits_exceeded')
        source.seek(0)
        try:
            with zipfile.ZipFile(source) as archive:
                for member in archive.infolist():
                    budget[0] -= member.file_size; budget[1] -= 1
                    if member.flag_bits & 1:
                        raise Detected('encrypted_archive')
                    if member.file_size > limit or min(budget) < 0:
                        raise Detected('archive_limits_exceeded')
                    if member.is_dir():
                        continue
                    with archive.open(member) as item:
                        header = item.read(4)
                        if header.startswith(b'PK'):
                            data = header + item.read(limit + 1)
                            if len(data) > limit:
                                raise Detected('archive_limits_exceeded')
                            check(io.BytesIO(data), depth + 1)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
            raise ScanFailure('archive_unscannable') from exc
    try:
        check(stream, 0)
    finally:
        stream.seek(position)


def scanner_version():
    try:
        with socket.create_connection((os.getenv('CANARY_CLAMAV_HOST', 'clamav'),
                positive_int('CANARY_CLAMAV_PORT', 3310)), timeout=2) as sock:
            sock.sendall(b'zVERSION\0')
            data = b''
            while b'\0' not in data:
                chunk = sock.recv(256)
                if not chunk or len(data) + len(chunk) > 1024:
                    raise ScanFailure('invalid_scanner_version')
                data += chunk
        version = data.split(b'\0', 1)[0].decode('ascii')
        _, sequence, stamp = version.split('/', 2)
        if not version.startswith('ClamAV ') or not sequence.isdigit():
            raise ValueError('invalid signature identity')
        updated = datetime.strptime(stamp.strip(), '%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - updated
        if age > timedelta(days=positive_int('CANARY_CLAMAV_MAX_SIGNATURE_AGE_DAYS', 7)) or age < -timedelta(days=1):
            raise ScanFailure('scanner_signatures_stale')
        return version
    except (OSError, ValueError, UnicodeError) as exc:
        raise ScanFailure('scanner_unavailable') from exc


def scan_stream(stream):
    """Bounded INSTREAM protocol; a partial/unknown/error response never passes.

    clamd must enable encrypted/limit alerts (see the bundled locked config).
    No paths or user filenames are sent to the scanner.
    """
    scanner_version()
    timeout = positive_int('CANARY_UPLOAD_SCAN_TIMEOUT_SECONDS', 30)
    deadline = time.monotonic() + timeout
    limit = positive_int('CANARY_UPLOAD_SCAN_MAX_BYTES', 26214400)
    try:
        with socket.create_connection((os.getenv('CANARY_CLAMAV_HOST', 'clamav'),
                positive_int('CANARY_CLAMAV_PORT', 3310)), timeout=timeout) as sock:
            def remaining():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise ScanFailure('timeout')
                sock.settimeout(left)
            remaining(); sock.sendall(b'zINSTREAM\0')
            total = 0
            while chunk := stream.read(65536):
                total += len(chunk)
                if total > limit:
                    raise ScanFailure('scan_size_limit')
                remaining(); sock.sendall(struct.pack('!I', len(chunk)) + chunk)
            remaining(); sock.sendall(b'\0\0\0\0')
            result = b''
            while b'\0' not in result:
                remaining(); chunk = sock.recv(1024)
                if not chunk or len(result) + len(chunk) > 4096:
                    raise ScanFailure('invalid_scanner_response')
                result += chunk
            response = result.split(b'\0', 1)[0]
            if response == b'stream: OK':
                validate_zip_limits(stream, limit)
                return
            if response.startswith(b'stream: ') and response.endswith(b' FOUND'):
                reason = 'encrypted_document' if b'Heuristics.Encrypted' in response else ('scan_limits_exceeded' if b'Heuristics.Limits.Exceeded' in response else 'scanner_detection')
                raise Detected(reason)
            raise ScanFailure('scan_incomplete')
    except (OSError, ValueError) as exc:
        raise ScanFailure('scanner_unavailable') from exc


def scan_bytes_before_processing(data):
    """Synchronous guard for replacement/template uploads that cannot be queued."""
    if not required():
        return
    import io
    try:
        scan_stream(io.BytesIO(data))
    except Detected as exc:
        raise HTTPException(422, 'Upload blocked by document security scanning') from exc
    except ScanFailure as exc:
        raise HTTPException(503, 'Upload not accepted: security scan could not complete') from exc


def stage_upload(upload):
    import fcntl
    root = quarantine_root()
    with (root / '.quota-lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        used = sum(p.stat().st_size for p in root.iterdir() if p.is_file() and not p.name.startswith('.'))
        capacity = positive_int('CANARY_QUARANTINE_MAX_BYTES', 1073741824)
        return _stage_upload_locked(upload, capacity - used)


def _stage_upload_locked(upload, remaining):
    from app.upload_limits import max_upload_bytes
    root = quarantine_root()
    token = uuid.uuid4().hex
    path = root / token
    total = 0
    limit = min(max_upload_bytes(), positive_int('CANARY_UPLOAD_SCAN_MAX_BYTES', 26214400))
    try:
        with path.open('xb') as dest:
            os.chmod(path, 0o600)
            while chunk := upload.file.read(65536):
                total += len(chunk)
                if total > remaining:
                    raise HTTPException(507, 'Upload quarantine is full; contact your administrator')
                if total > limit:
                    raise HTTPException(413, 'Upload exceeds the document scanning size limit')
                dest.write(chunk)
            dest.flush(); os.fsync(dest.fileno())
        from app.document_durability import sync_path
        sync_path(path, root)
        return token, total, hashlib.sha256(path.read_bytes()).hexdigest()
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def mark_pending(db, row, token, checksum, context):
    row.scan_state = 'pending'
    row.scan_quarantine_key = token
    row.scan_checksum = checksum
    row.scan_context = context
    row.scan_attempts = 0
    db.add(row)
    db.execute(text("SELECT pg_notify('canary_upload_scan', '')"))


def enqueue_case_upload(db, *, upload, file_id, case_id, user, paths, parent_file_id,
                        operation_id, fingerprint, context):
    from app.models import File, FileCategory
    from app.upload_receipts import UploadReceipt
    from app.deps import require_case_access
    from app.audit import log_event
    require_case_access(case_id, user, db)
    token, size, checksum = stage_upload(upload)
    row = File(id=file_id, case_id=case_id, owner_id=user.id, category=FileCategory.case_document,
        storage_path=paths.rel_path, folder_path=paths.folder_path, parent_file_id=parent_file_id,
        original_filename=Path(upload.filename or 'upload.bin').name,
        mime_type=upload.content_type or 'application/octet-stream', size_bytes=size,
        version=1, checksum=checksum)
    import mimetypes
    if row.mime_type.split(';')[0] == 'application/octet-stream':
        row.mime_type = mimetypes.guess_type(row.original_filename)[0] or row.mime_type
    mark_pending(db, row, token, checksum, dict(context, actor_id=str(user.id)))
    response = dict(id=str(row.id), case_id=str(case_id), original_filename=row.original_filename,
                    mime_type=row.mime_type, size_bytes=size, scan_state='pending')
    if operation_id:
        db.add(UploadReceipt(id=operation_id, fingerprint=fingerprint, response=response))
    log_event(db, actor_user_id=user.id, action='case.file.upload', entity_type='file', entity_id=str(row.id),
              meta={'case_id': str(case_id), 'filename': row.original_filename, 'size_bytes': size, 'scan_state': 'pending'})
    log_event(db, actor_user_id=user.id, action='file.scan.queued', entity_type='file', entity_id=str(row.id))
    # Retain quarantine on ambiguous commit; never delete a possibly committed upload.
    db.commit()
    return response


def _authorize_release(db, row):
    from app.models import User, ContactPortalGrant, Case
    from app.deps import require_case_access
    from app.case_folder_service import _folder_destination_exists
    context = row.scan_context or {}
    db.scalar(select(Case).where(Case.id == row.case_id).with_for_update(read=True))
    if context.get('portal_session'):
        from app.security import PortalSessionPayload
        db.info['portal_session'] = PortalSessionPayload(**context['portal_session'])
    if context.get('grant_id'):
        from app.portal_policy import authorize, fresh
        from app.portal_browse_service import get_grant_for_contact, ensure_upload_folder_allowed
        authorize(db, row.case_id, lock=True)
        grant = fresh(db, ContactPortalGrant, uuid.UUID(context['grant_id']), lock=True)
        if grant is None:
            raise HTTPException(403, 'Upload grant revoked')
        grant = get_grant_for_contact(db, contact_id=uuid.UUID(context['contact_id']), grant_id=grant.id)
        if grant.case_id != row.case_id:
            raise HTTPException(403, 'Upload destination changed')
        ensure_upload_folder_allowed(grant=grant, folder=row.folder_path or '')
    else:
        actor = db.scalar(select(User).where(User.id == uuid.UUID(context['actor_id'])).with_for_update(read=True))
        if actor is None or not actor.is_active:
            raise HTTPException(403, 'Uploader inactive')
        require_case_access(row.case_id, actor, db)
    if row.folder_path and not _folder_destination_exists(db, row.case_id, row.folder_path):
        raise HTTPException(403, 'Upload folder removed')


def _promote(db, row, path):
    from app.file_storage import FILES_ROOT, stored_file_checksum
    from app.document_durability import safe_path, sync_path
    from app.file_eml_service import refresh_root_eml_mail_metadata
    from app.mail_filing_lookup import message_id_from_email
    from app.models import User
    context = row.scan_context or {}
    candidate = path
    expected_checksum = row.scan_checksum
    if row.original_filename.lower().endswith('.msg'):
        from app.outlook_msg import outlook_msg_path_to_eml_bytes
        data = outlook_msg_path_to_eml_bytes(path)
        import io
        scan_stream(io.BytesIO(data))
        expected_checksum = hashlib.sha256(data).hexdigest()
        candidate = path.with_suffix('.eml')
        candidate.write_bytes(data)
        row.original_filename = Path(row.original_filename).stem + '.eml'
        row.mime_type = 'message/rfc822'
    # Unique immutable destination. DB publication is the only access gate;
    # crash/rollback leaves an unreferenced candidate, never readable pending bytes.
    relative = str(Path('.scanned') / str(row.id) / uuid.uuid4().hex / Path(row.original_filename).name)
    target = safe_path(FILES_ROOT, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, target)
    sync_path(target, FILES_ROOT)
    row._storage_path = relative
    row.checksum = stored_file_checksum(target)
    if row.checksum != expected_checksum:
        raise Detected("upload_integrity_failure")
    row.size_bytes = target.stat().st_size
    if row.original_filename.lower().endswith('.eml') or row.mime_type.split(';')[0] == 'message/rfc822':
        row.mime_type = 'message/rfc822'
        if row.parent_file_id is None:
            row.source_imap_mbox = context.get('source_imap_mbox')
            row.source_imap_uid = context.get('source_imap_uid')
            row.source_outlook_item_id = context.get('outlook_item_id')
            row.source_outlook_conversation_id = context.get('outlook_conversation_id')
            actor = db.get(User, row.owner_id)
            refresh_root_eml_mail_metadata(row, target, uploader_email=actor.email if actor else None)
            row.source_internet_message_id = message_id_from_email(target)
    row.scan_context = dict(context, scanner_version=scanner_version())
    row.scan_state = 'clean'
    row.scan_error = None
    row.scan_finished_at = datetime.now(timezone.utc)
    row.scan_quarantine_key = None
    from app.firm_module_runtime import process_document_uploaded
    if not row.uploaded_via_portal:
        process_document_uploaded(db, case_id=row.case_id, file_id=row.id,
                                  actor_user_id=row.owner_id, filename=row.original_filename)
    from app.audit import log_event
    log_event(db, actor_user_id=None, action='file.scan.clean', entity_type='file',
              entity_id=str(row.id), meta={'checksum': row.checksum})


def scan_one(db):
    """A transaction lock claims one item; death releases it for another worker."""
    if not required():
        return False
    from app.models import File
    now = datetime.now(timezone.utc)
    row = db.execute(select(File).where(File.scan_state.in_(['pending', 'error']),
        File.scan_attempts < 3, or_(File.scan_retry_at.is_(None), File.scan_retry_at <= now))
        .order_by(File.created_at).with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
    if row is None:
        db.rollback()
        return False
    token = row.scan_quarantine_key
    if not token or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        row.scan_state = 'blocked'; row.scan_error = 'invalid_quarantine_reference'; db.commit(); return True
    path = quarantine_root() / token
    row.scan_attempts += 1
    try:
        if path.is_symlink():
            raise Detected("upload_integrity_failure")
        with path.open('rb') as stream:
            before = hashlib.file_digest(stream, 'sha256').hexdigest()
            if before != row.scan_checksum:
                raise Detected('upload_integrity_failure')
            stream.seek(0); scan_stream(stream)
        if hashlib.sha256(path.read_bytes()).hexdigest() != before:
            raise Detected('upload_integrity_failure')
        with db.begin_nested():
            _authorize_release(db, row)
            _promote(db, row, path)
    except Detected as exc:
        row.scan_state = 'blocked'; row.scan_error = str(exc)
    except HTTPException:
        row.scan_state = 'blocked'; row.scan_error = 'authorization_changed'
    except Exception:
        # Don't return scanner/internal exception details to clients.
        row.scan_state = 'error'; row.scan_error = 'scan_incomplete'
        row.scan_retry_at = now + timedelta(seconds=30 * row.scan_attempts)
    from app.audit import log_event
    if row.scan_state != 'clean':
        log_event(db, actor_user_id=None, action='file.scan.' + row.scan_state,
                  entity_type='file', entity_id=str(row.id), meta={'reason': row.scan_error})
    clean = row.scan_state == 'clean'
    db.commit()
    db.info.pop('portal_session', None)
    if clean:
        path.unlink(missing_ok=True)
        path.with_suffix('.eml').unlink(missing_ok=True)
    return True


def main():
    if os.getenv('CANARY_UPLOAD_SCAN_WORKER_ENABLED', '0') != '1':
        raise SystemExit('Upload scan worker is disabled')
    validate_config()
    if not required():
        raise SystemExit('Upload scanning is disabled; pending files remain quarantined')
    from app.db import SessionLocal, engine
    # LISTEN is an optimisation only. The database queue survives lost wakeups,
    # process restarts and downtime. Recheck at least once per second.
    import psycopg
    with psycopg.connect(engine.url.set(drivername='postgresql').render_as_string(hide_password=False), autocommit=True) as raw:
        raw.execute('LISTEN canary_upload_scan')
        while True:
            with SessionLocal() as db:
                if scan_one(db):
                    continue
            for _ in raw.notifies(timeout=1, stop_after=1):
                break


def scan_upload_before_processing(upload):
    if not required():
        return
    position = upload.file.tell()
    try:
        upload.file.seek(0)
        try:
            scan_stream(upload.file)
        except Detected as exc:
            raise HTTPException(422, 'Upload blocked by document security scanning') from exc
        except ScanFailure as exc:
            raise HTTPException(503, 'Upload not accepted: security scan could not complete') from exc
    finally:
        upload.file.seek(position)


async def scan_upload_async(upload):
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(scan_upload_before_processing, upload)


async def scan_bytes_async(data):
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(scan_bytes_before_processing, data)


if __name__ == '__main__':
    main()
