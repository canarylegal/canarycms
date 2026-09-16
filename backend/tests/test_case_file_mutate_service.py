"""Case file rename / move guards (extension lock, system markers, missing folder)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.case_file_mutate_service import move_case_file, rename_case_file
from app.case_folder_service import _FOLDER_GONE_DETAIL
from app.file_storage import case_file_paths
from app.models import (
    AuditEvent,
    Base,
    Case,
    File as DbFile,
    FileCategory,
    FileEditSession,
    User,
    UserRole,
)
from app.schemas import CaseFileMoveUpdate, CaseFileRenameUpdate
from tests.ledger_test_helpers import add_case, add_user


def _session_with_tables() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    try:
        for table in (User.__table__, Case.__table__, DbFile.__table__, FileEditSession.__table__, AuditEvent.__table__):
            table.create(engine)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


@pytest.fixture
def mutate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    files = (tmp_path / "files").resolve()
    files.mkdir()
    monkeypatch.setattr("app.file_storage.FILES_ROOT", files)
    monkeypatch.setattr("app.case_file_mutate_service.FILES_ROOT", files)
    db = _session_with_tables()
    try:
        yield db, files
    finally:
        db.close()


def _add_case_document(
    db: Session,
    *,
    case: Case,
    user: User,
    filename: str,
    folder_path: str = "",
    category: FileCategory = FileCategory.case_document,
) -> DbFile:
    file_id = uuid.uuid4()
    paths = case_file_paths(
        case_id=case.id,
        file_id=file_id,
        original_filename=filename,
        folder_path=folder_path,
    )
    paths.abs_path.write_bytes(b"hello")
    row = DbFile(
        id=file_id,
        case_id=case.id,
        owner_id=user.id,
        category=category,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        is_pinned=False,
        original_filename=filename,
        mime_type="application/octet-stream",
        size_bytes=5,
        version=1,
        checksum=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_rename_rejects_extension_change(mutate_db) -> None:
    db, _files = mutate_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    row = _add_case_document(db, case=case, user=user, filename="letter.docx")

    with pytest.raises(HTTPException) as exc:
        rename_case_file(
            case.id,
            row.id,
            CaseFileRenameUpdate(original_filename="letter.pdf"),
            user,
            db,
        )
    assert exc.value.status_code == 400
    assert "extension" in str(exc.value.detail).lower()


def test_rename_rejects_system_folder_marker(mutate_db) -> None:
    db, _files = mutate_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    row = _add_case_document(
        db,
        case=case,
        user=user,
        filename="Contracts",
        folder_path="Contracts",
        category=FileCategory.system,
    )
    row.mime_type = "application/x-directory"
    db.add(row)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        rename_case_file(
            case.id,
            row.id,
            CaseFileRenameUpdate(original_filename="Renamed"),
            user,
            db,
        )
    assert exc.value.status_code == 400
    assert "folder marker" in str(exc.value.detail).lower()


def test_move_missing_folder_returns_409(mutate_db) -> None:
    db, _files = mutate_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    row = _add_case_document(db, case=case, user=user, filename="note.txt")

    with pytest.raises(HTTPException) as exc:
        move_case_file(
            case.id,
            row.id,
            CaseFileMoveUpdate(folder_path="DoesNotExist"),
            user,
            db,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == _FOLDER_GONE_DETAIL
