"""Case folder create / rename guards and destination helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.case_folder_service import (
    _folder_destination_exists,
    create_case_folder,
    rename_case_folder,
)
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
from app.schemas import CaseFolderCreate, CaseFolderRenameUpdate
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
def folder_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    files = (tmp_path / "files").resolve()
    files.mkdir()
    monkeypatch.setattr("app.file_storage.FILES_ROOT", files)
    db = _session_with_tables()
    try:
        yield db, files
    finally:
        db.close()


def test_create_case_folder_inserts_marker(folder_db) -> None:
    db, files = folder_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)

    out = create_case_folder(case.id, CaseFolderCreate(folder_path="Contracts"), user, db)
    assert out == {"folder_path": "Contracts"}
    assert _folder_destination_exists(db, case.id, "Contracts") is True

    marker = db.execute(select(DbFile).where(DbFile.case_id == case.id)).scalar_one()
    assert marker.category == FileCategory.system
    assert marker.mime_type == "application/x-directory"
    assert marker.folder_path == "Contracts"
    assert (files / marker.storage_path).is_file()


def test_create_case_folder_idempotent(folder_db) -> None:
    db, _files = folder_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    create_case_folder(case.id, CaseFolderCreate(folder_path="Docs"), user, db)
    again = create_case_folder(case.id, CaseFolderCreate(folder_path="Docs"), user, db)
    assert again == {"folder_path": "Docs"}
    rows = db.execute(select(DbFile).where(DbFile.case_id == case.id)).scalars().all()
    assert len(rows) == 1


def test_rename_root_folder_rejected(folder_db) -> None:
    db, _files = folder_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)

    with pytest.raises(HTTPException) as exc:
        rename_case_folder(
            case.id,
            CaseFolderRenameUpdate(old_folder_path="", new_folder_path="Elsewhere"),
            user,
            db,
        )
    assert exc.value.status_code == 400
    assert "root" in str(exc.value.detail).lower()


def test_folder_destination_exists_root_always(folder_db) -> None:
    db, _files = folder_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    assert _folder_destination_exists(db, case.id, "") is True


def test_folder_destination_missing_without_rows(folder_db) -> None:
    db, _files = folder_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    assert _folder_destination_exists(db, case.id, "Gone") is False


def test_folder_destination_exists_with_file_under_path(folder_db) -> None:
    db, _files = folder_db
    user = add_user(db, role=UserRole.admin)
    case = add_case(db, fee_earner_user_id=user.id)
    db.add(
        DbFile(
            id=uuid.uuid4(),
            case_id=case.id,
            owner_id=user.id,
            category=FileCategory.case_document,
            storage_path=f"cases/{case.id}/x.txt",
            folder_path="Inbox",
            is_pinned=False,
            original_filename="x.txt",
            mime_type="text/plain",
            size_bytes=1,
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    assert _folder_destination_exists(db, case.id, "Inbox") is True
