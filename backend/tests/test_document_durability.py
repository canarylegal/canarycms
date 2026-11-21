"""Failure injection at the filesystem/database boundary; no live dependencies."""
import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.document_durability import lock_document, retain_document, stage_document_bytes
from app.document_recovery import restore_document
from app.models import DocumentRecovery, File, UserRole
from app.onlyoffice_force_save import oo_force_save_arm, oo_save_status
from tests.test_cl18_release_edit_save import _session, _user, _case, _file, _open_session


@pytest.fixture
def document(tmp_path):
    db = _session()
    user = _user(db)
    user.role = UserRole.admin
    case = _case(db, user)
    row = _file(db, case, user)
    row.original_filename = 'note.txt'
    row.mime_type = 'text/plain'
    row.storage_path = 'note.txt'
    (tmp_path / row.storage_path).write_bytes(b'original')
    row.size_bytes = 8
    db.commit()
    yield db, user, case, row, tmp_path
    db.close()


def test_save_rollback_preserves_original_and_retry_can_commit(document, monkeypatch):
    db, _, _, row, root = document
    old_path = row.storage_path
    candidate = stage_document_bytes(db, lock_document(db, row), b'new', root=root)
    original_commit = db.commit
    monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('commit failed')))
    with pytest.raises(RuntimeError):
        db.commit()
    db.rollback()
    assert row.storage_path == old_path
    assert (root / row.storage_path).read_bytes() == b'original'
    assert candidate.read_bytes() == b'new'
    monkeypatch.setattr(db, 'commit', original_commit)
    stage_document_bytes(db, lock_document(db, row), b'retry', root=root)
    row.version += 1
    db.commit()
    assert (root / row.storage_path).read_bytes() == b'retry'
    record = db.scalar(select(DocumentRecovery))
    assert (root / record.storage_path).read_bytes() == b'original'


def test_write_failure_keeps_database_pointer_and_original(document, monkeypatch):
    from app import document_durability as durability
    db, _, _, row, root = document
    old = row.storage_path
    monkeypatch.setattr(durability, 'sync_path', MagicMock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):
        stage_document_bytes(db, row, b'never published', root=root)
    db.rollback()
    assert row.storage_path == old
    assert (root / old).read_bytes() == b'original'


def test_ambiguous_commit_does_not_remove_published_bytes(document):
    db, _, _, row, root = document
    fid = row.id
    candidate = stage_document_bytes(db, row, b'committed', root=root)
    db.commit()  # Simulate DB commit succeeding, followed by loss of acknowledgement.
    db.rollback()
    with Session(db.get_bind()) as restarted:
        saved = restarted.get(File, fid)
        assert (root / saved.storage_path) == candidate
        assert candidate.read_bytes() == b'committed'
        archive = restarted.scalar(select(DocumentRecovery))
        assert (root / archive.storage_path).read_bytes() == b'original'


def test_deleted_document_can_be_restored_after_new_session(document, monkeypatch):
    from app import case_file_mutate_service as service
    db, user, case, row, root = document
    monkeypatch.setattr(service, 'FILES_ROOT', root)
    fid, uid = row.id, user.id
    service.delete_case_file(case.id, fid, user, db)
    record = db.scalar(select(DocumentRecovery))
    rid = record.id
    assert db.get(File, fid) is None
    with Session(db.get_bind()) as restarted:
        restore_document(restarted, rid, root=root, actor_id=uid)
        restarted.commit()
        restored = restarted.get(File, fid)
        assert (root / restored.storage_path).read_bytes() == b'original'
        with pytest.raises(HTTPException, match='already exists'):
            restore_document(restarted, rid, root=root, actor_id=uid)


def test_delete_commit_failure_keeps_document_readable(document, monkeypatch):
    from app import case_file_mutate_service as service
    db, user, case, row, root = document
    fid = row.id
    monkeypatch.setattr(service, 'FILES_ROOT', root)
    monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('db unavailable')))
    with pytest.raises(RuntimeError):
        service.delete_case_file(case.id, fid, user, db)
    db.rollback()
    restored = db.get(File, fid)
    assert (root / restored.storage_path).read_bytes() == b'original'


def test_corrupt_archive_refuses_restore(document):
    db, user, _, row, root = document
    record = retain_document(db, row, root=root, kind='version')
    db.commit()
    (root / record.storage_path).write_bytes(b'corrupted')
    with pytest.raises(HTTPException, match='checksum'):
        restore_document(db, record.id, root=root, actor_id=user.id, expected_version=1)
    db.rollback()
    assert (root / row.storage_path).read_bytes() == b'original'


def test_unrelated_version_change_and_stale_attempt_do_not_confirm(document):
    db, _, _, row, _ = document
    base = oo_force_save_arm(db, row, 'editor-key')
    old = row.oo_save_attempt_id
    row.version += 1
    db.commit()
    assert not oo_save_status(row, base, old)['saved']
    oo_force_save_arm(db, row, 'editor-key')
    row.oo_save_state = 'confirmed'
    assert not oo_save_status(row, base, old)['saved']
    assert not oo_save_status(row, base)['saved']


@pytest.mark.asyncio
@pytest.mark.parametrize('fail_commit', [False, True])
async def test_browser_save_only_confirms_after_durable_commit(document, monkeypatch, fail_commit):
    from app.routers import onlyoffice as service
    db, user, case, row, root = document
    _open_session(db, case, row, user)
    base = oo_force_save_arm(db, row, 'editor-key')
    attempt = row.oo_save_attempt_id
    monkeypatch.setattr(service, 'FILES_ROOT', root)
    monkeypatch.setattr(service, 'ensure_files_root', lambda: None)
    monkeypatch.setattr(service, 'path_is_under_files_root', lambda p: p.is_relative_to(root))
    monkeypatch.setattr(service, '_fetch_onlyoffice_download_bytes', AsyncMock(return_value=b'edited'))
    monkeypatch.setattr('app.quote_portal_service.supersede_pending_quote_deliveries', lambda *a: None)
    if fail_commit:
        monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('db unavailable')))
        with pytest.raises(RuntimeError):
            await service.persist_onlyoffice_browser_url_to_file(db, row, browser_url='unused',
                case_id=case.id, precedent_id=None, actor_user_id=user.id, attempt_id=attempt)
        db.rollback()
        assert not oo_save_status(row, base, attempt)['saved']
        assert (root / row.storage_path).read_bytes() == b'original'
    else:
        await service.persist_onlyoffice_browser_url_to_file(db, row, browser_url='unused',
            case_id=case.id, precedent_id=None, actor_user_id=user.id, attempt_id=attempt)
        assert oo_save_status(row, base, attempt)['saved']
        assert (root / row.storage_path).read_bytes() == b'edited'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['success', 'commit_failure', 'duplicate', 'stale', 'no_url', 'released', 'key_mismatch', 'download_failure'])
async def test_callback_failure_paths(document, monkeypatch, mode):
    from app.routers import onlyoffice as service
    db, user, case, row, root = document
    session = _open_session(db, case, row, user)
    session.document_key = 'editor-key'
    db.commit()
    base = oo_force_save_arm(db, row, 'editor-key')
    attempt = row.oo_save_attempt_id
    if mode == 'released':
        from app.onlyoffice_case_file_service import release_desktop_edit
        release_desktop_edit(case.id, row.id, user, db)
    if mode == 'stale':
        oo_force_save_arm(db, row, 'editor-key')
    payload = {'status': 6, 'key': 'other-key' if mode == 'key_mismatch' else 'editor-key',
               'url': 'http://onlyoffice/cache/doc', 'userdata': str(attempt)}
    if mode == 'no_url':
        payload.pop('url')
    request = MagicMock()
    request.body = AsyncMock(return_value=json.dumps(payload).encode())
    monkeypatch.setattr(service, 'FILES_ROOT', root)
    monkeypatch.setattr(service, 'ensure_files_root', lambda: None)
    monkeypatch.setattr(service, 'path_is_under_files_root', lambda p: p.is_relative_to(root))
    monkeypatch.setattr(service, '_callback_fetch_url_or_reject', lambda u: u)
    monkeypatch.setattr(service, '_decode_callback_payload', lambda req, body: body)
    download = AsyncMock(return_value=None if mode == 'download_failure' else b'callback edit')
    monkeypatch.setattr(service, '_download_oo_document_bytes', download)
    monkeypatch.setattr('app.quote_portal_service.supersede_pending_quote_deliveries', lambda *a: None)
    async def callback():
        return await service.onlyoffice_callback(request, case_id=case.id, file_id=row.id,
            precedent_id=None, fee_scale_id=None, firm_letterhead_kind=None, db=db)
    if mode == 'commit_failure':
        monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('failed commit')))
        with pytest.raises(RuntimeError):
            await callback()
        db.rollback()
    else:
        result = await callback()
        assert result == {'error': 1 if mode == 'download_failure' else 0}
    if mode in ('success', 'duplicate'):
        assert oo_save_status(row, base, attempt)['saved']
        assert (root / row.storage_path).read_bytes() == b'callback edit'
        if mode == 'duplicate':
            await callback()
            assert row.version == base + 1
            download.assert_awaited_once()
    else:
        db.refresh(row)
        assert not oo_save_status(row, base, attempt)['saved']
        assert row.version == base
        assert (root / row.storage_path).read_bytes() == b'original'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['success', 'commit_failure', 'revoked_during_upload'])
async def test_webdav_failure_paths(document, monkeypatch, mode):
    from app.routers import webdav as service
    db, user, case, row, root = document
    session = _open_session(db, case, row, user)
    monkeypatch.setattr(service, 'FILES_ROOT', root)
    monkeypatch.setattr(service, 'ensure_files_root', lambda: None)
    monkeypatch.setattr(service, 'path_is_under_files_root', lambda p: p.is_relative_to(root))
    monkeypatch.setattr('app.quote_portal_service.supersede_pending_quote_deliveries', lambda *a: None)
    request = MagicMock()
    request.headers = {}
    request.url.path = "/webdav/sessions/test/note.txt"
    async def stream():
        yield b'webdav edit'
        if mode == 'revoked_during_upload':
            from datetime import datetime, timezone
            session.released_at = datetime.now(timezone.utc)
            db.commit()
    request.stream = stream
    if mode == 'commit_failure':
        monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('failed commit')))
    if mode == 'success':
        result = await service.webdav_put_file(request, session.token, row.original_filename, db)
        assert result.status_code == 204
        assert (root / row.storage_path).read_bytes() == b'webdav edit'
    else:
        with pytest.raises((RuntimeError, HTTPException)):
            await service.webdav_put_file(request, session.token, row.original_filename, db)
        db.rollback()
        assert (root / row.storage_path).read_bytes() == b'original'
        assert row.version == 1


def test_version_restore_retains_displaced_version_and_checks_expected_version(document):
    db, user, _, row, root = document
    stage_document_bytes(db, row, b'new edit', root=root)
    row.version = 2
    db.commit()
    record = db.scalar(select(DocumentRecovery))
    with pytest.raises(HTTPException):
        restore_document(db, record.id, root=root, actor_id=user.id, expected_version=1)
    db.rollback()
    restore_document(db, record.id, root=root, actor_id=user.id, expected_version=2)
    db.commit()
    assert row.version == 3
    assert (root / row.storage_path).read_bytes() == b'original'
    displaced = db.scalar(select(DocumentRecovery).where(DocumentRecovery.kind == 'restore'))
    assert (root / displaced.storage_path).read_bytes() == b'new edit'


def test_folder_delete_failure_preserves_every_document(document, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import case_folder_service as service
    from app.schemas import CaseFolderDeleteUpdate
    db, user, case, row, root = document
    row.folder_path = 'archive'
    row.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    monkeypatch.setattr('app.file_storage.FILES_ROOT', root)
    monkeypatch.setattr(service, '_lock_case_folder_ops', lambda *a, **kw: None)
    monkeypatch.setattr(service, '_db_now', lambda *a: datetime.now(timezone.utc))
    monkeypatch.setattr('app.portal_service.revoke_portal_grants_for_deleted_folder', lambda *a, **kw: 0)
    monkeypatch.setattr(db, 'commit', MagicMock(side_effect=RuntimeError('commit failed')))
    with pytest.raises(RuntimeError):
        service.delete_case_folder(case.id, CaseFolderDeleteUpdate(folder_path='archive'), user, db)
    db.rollback()
    assert (root / row.storage_path).read_bytes() == b'original'
    assert row.folder_path == 'archive'


def test_recovery_can_repair_missing_current_bytes(document):
    db, user, _, row, root = document
    record = retain_document(db, row, root=root, kind='version')
    db.commit()
    (root / row.storage_path).unlink()
    restore_document(db, record.id, root=root, actor_id=user.id, expected_version=1)
    db.commit()
    assert (root / row.storage_path).read_bytes() == b'original'


def test_save_status_route_serializes_attempt_states():
    from typing import get_type_hints
    from pydantic import TypeAdapter
    from app.routers.files import oo_save_status as route
    adapter = TypeAdapter(get_type_hints(route)['return'])
    for state in ['pending', 'confirmed', 'failed', 'superseded', None]:
        result = adapter.validate_python({'saved': False, 'version': 1, 'state': state})
        assert result['state'] == state


@pytest.mark.asyncio
async def test_pdf_export_remains_a_separate_document(document, monkeypatch):
    from app.routers import onlyoffice as router
    from app.onlyoffice_case_file_service import oo_export_pdf
    from app.schemas import OoExportPdfIn
    db, user, case, row, root = document
    _open_session(db, case, row, user)
    monkeypatch.setattr('app.file_storage.FILES_ROOT', root)
    monkeypatch.setattr(router, 'FILES_ROOT', root)
    monkeypatch.setattr(router, '_fetch_onlyoffice_download_bytes', AsyncMock(return_value=b'%PDF-1.7\nfixture'))
    monkeypatch.setattr(router, 'fix_pdf_form_need_appearances', lambda data: data)
    result = await oo_export_pdf(case.id, row.id, OoExportPdfIn(browser_url='https://office/cache/pdf'), user, db)
    exported = db.get(File, result.file_id)
    assert exported.id != row.id
    assert exported.mime_type == 'application/pdf'
    assert (root / exported.storage_path).read_bytes().startswith(b'%PDF')
    assert (root / row.storage_path).read_bytes() == b'original'
