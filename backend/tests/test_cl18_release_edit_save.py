"""CL-18: OnlyOffice must not persist after edit-session release."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.desktop_edit_session import (
    get_active_edit_session_for_file,
    release_edit_sessions_for_user,
    require_user_active_edit_session,
)
from app.models import (
    Base,
    Case,
    CaseLockMode,
    CaseStatus,
    File as DbFile,
    FileCategory,
    FileEditSession,
    User,
)
from app.onlyoffice_case_file_service import oo_force_save, oo_persist_download, release_desktop_edit
from app.schemas import OoPersistDownloadIn


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (User.__table__, Case.__table__, DbFile.__table__, FileEditSession.__table__):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def _user(db: Session) -> User:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    user = User(
        id=uid,
        email=f"u-{uid.hex[:8]}@example.com",
        password_hash="x",
        display_name="Editor",
        initials="ED",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _case(db: Session, fee: User) -> Case:
    now = datetime.now(timezone.utc)
    case = Case(
        id=uuid.uuid4(),
        case_number="000176",
        title="CL-18",
        fee_earner_user_id=fee.id,
        created_by=fee.id,
        status=CaseStatus.open,
        lock_mode=CaseLockMode.none,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def _file(db: Session, case: Case, user: User, *, pending: bool = False) -> DbFile:
    fid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    row = DbFile(
        id=fid,
        case_id=case.id,
        owner_id=user.id,
        original_filename="doc.docx",
        storage_path=f"cases/{case.id}/{fid}/doc.docx",
        folder_path="",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=10,
        category=FileCategory.case_document,
        version=1,
        oo_force_save_pending=pending,
        oo_compose_pending=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _open_session(db: Session, case: Case, row: DbFile, user: User) -> FileEditSession:
    now = datetime.now(timezone.utc)
    sess = FileEditSession(
        id=uuid.uuid4(),
        token="tok-" + uuid.uuid4().hex,
        file_id=row.id,
        case_id=case.id,
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(hours=2),
        released_at=None,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def test_require_active_session_rejects_after_release() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    row = _file(db, case, user)
    sess = _open_session(db, case, row, user)

    assert require_user_active_edit_session(db, row.id, user).id == sess.id

    sess.released_at = datetime.now(timezone.utc)
    db.add(sess)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        require_user_active_edit_session(db, row.id, user)
    assert exc.value.status_code == 409
    assert get_active_edit_session_for_file(db, row.id) is None


@pytest.mark.asyncio
async def test_oo_force_save_arm_rejects_without_session() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    row = _file(db, case, user)

    with pytest.raises(HTTPException) as exc:
        await oo_force_save(
            case.id,
            row.id,
            doc_key="k",
            phase="arm",
            base_version=None,
            user=user,
            db=db,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_oo_persist_download_rejects_without_session() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    row = _file(db, case, user)

    with pytest.raises(HTTPException) as exc:
        await oo_persist_download(
            case.id,
            row.id,
            body=OoPersistDownloadIn(browser_url="https://example.test/x"),
            user=user,
            db=db,
        )
    assert exc.value.status_code == 409


def test_release_edit_clears_force_save_pending_and_bumps_version(monkeypatch) -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    row = _file(db, case, user, pending=True)
    _open_session(db, case, row, user)
    monkeypatch.setattr("app.onlyoffice_case_file_service.log_event", lambda *a, **k: None)

    release_desktop_edit(case.id, row.id, user, db)
    db.refresh(row)
    assert row.oo_force_save_pending is False
    assert row.version == 2
    assert get_active_edit_session_for_file(db, row.id) is None


def test_release_sessions_for_user_clears_force_save_pending() -> None:
    db = _session()
    user = _user(db)
    case = _case(db, user)
    row = _file(db, case, user, pending=True)
    _open_session(db, case, row, user)

    n = release_edit_sessions_for_user(db, user.id, case_id=case.id)
    db.commit()
    db.refresh(row)
    assert n == 1
    assert row.oo_force_save_pending is False
    assert row.version == 2


@pytest.mark.asyncio
async def test_callback_refuses_byte_persist_without_session(tmp_path, monkeypatch) -> None:
    """Regression for CL-18: force-save pending + DS url must not write after release."""
    from app.routers import onlyoffice as oo

    db = _session()
    user = _user(db)
    case = _case(db, user)
    row = _file(db, case, user, pending=True)

    abs_path = tmp_path / "doc.docx"
    abs_path.write_bytes(b"ORIGINAL_BYTES_XXXX")
    row.storage_path = "doc.docx"
    db.add(row)
    db.commit()

    monkeypatch.setattr(oo, "FILES_ROOT", tmp_path)
    monkeypatch.setattr(oo, "ensure_files_root", lambda: None)
    monkeypatch.setattr(oo, "path_is_under_files_root", lambda p: True)
    monkeypatch.setattr(oo, "_rewrite_oo_download_url", lambda u: u)
    monkeypatch.setattr(oo, "finalize_stored_docx_bytes", lambda data, **kw: data)
    monkeypatch.setattr(oo, "_callback_resolve_file_row", lambda *a, **k: row)
    monkeypatch.setattr(
        oo,
        "_decode_callback_payload",
        lambda req, body: body if isinstance(body, dict) else {"status": 6, "url": "http://ds/cache/x"},
    )
    monkeypatch.setattr(oo, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.quote_portal_service.supersede_pending_quote_deliveries",
        lambda *a, **k: None,
    )

    class _Resp:
        content = b"POST_RELEASE_SHOULD_NOT_LAND"

        def raise_for_status(self) -> None:
            return None

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return _Resp()

    monkeypatch.setattr(oo.httpx, "AsyncClient", lambda **kw: _Client())

    req = MagicMock()

    async def _body() -> bytes:
        return b'{"status":6,"url":"http://ds/cache/x"}'

    req.body = _body

    out = await oo.onlyoffice_callback(
        request=req,
        case_id=case.id,
        file_id=row.id,
        db=db,
    )
    assert out == {"error": 0}
    assert abs_path.read_bytes() == b"ORIGINAL_BYTES_XXXX"
    db.refresh(row)
    assert row.oo_force_save_pending is False
    assert row.version == 2