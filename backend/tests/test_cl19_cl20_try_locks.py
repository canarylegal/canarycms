"""CL-19 / CL-20: concurrent rename and invoice approve/void try-locks."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.case_file_mutate_service import (
    _FILE_RENAME_BUSY_DETAIL,
    _try_lock_file_rename,
)
from app.invoice_service import (
    _INVOICE_BUSY_DETAIL,
    _try_lock_invoice,
)


def test_try_lock_file_rename_raises_409_when_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    db.get_bind.return_value = bind
    db.execute.return_value.scalar.return_value = False

    with pytest.raises(HTTPException) as exc:
        _try_lock_file_rename(db, uuid.uuid4())
    assert exc.value.status_code == 409
    assert exc.value.detail == _FILE_RENAME_BUSY_DETAIL


def test_try_lock_file_rename_noop_on_sqlite() -> None:
    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "sqlite"
    db.get_bind.return_value = bind
    _try_lock_file_rename(db, uuid.uuid4())
    db.execute.assert_not_called()


def test_try_lock_invoice_raises_409_when_busy() -> None:
    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    db.get_bind.return_value = bind
    db.execute.return_value.scalar.return_value = False

    with pytest.raises(HTTPException) as exc:
        _try_lock_invoice(db, uuid.uuid4())
    assert exc.value.status_code == 409
    assert exc.value.detail == _INVOICE_BUSY_DETAIL


def test_try_lock_invoice_noop_on_sqlite() -> None:
    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "sqlite"
    db.get_bind.return_value = bind
    _try_lock_invoice(db, uuid.uuid4())
    db.execute.assert_not_called()


def test_rename_conflicts_when_expected_name_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    """CL-19 CAS: client still asserts the pre-race name after another rename committed."""
    from datetime import datetime, timezone

    from app.case_file_mutate_service import rename_case_file
    from app.models import File as DbFile, FileCategory
    from app.schemas import CaseFileRenameUpdate

    case_id = uuid.uuid4()
    file_id = uuid.uuid4()
    user = MagicMock(id=uuid.uuid4())

    locked = DbFile(
        id=file_id,
        case_id=case_id,
        owner_id=user.id,
        category=FileCategory.case_document,
        folder_path="",
        original_filename="winner-name.txt",
        storage_path="cases/x/winner-name.txt",
        mime_type="text/plain",
        size_bytes=1,
        version=2,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db = MagicMock()
    bind = MagicMock()
    bind.dialect.name = "sqlite"
    db.get_bind.return_value = bind
    result = MagicMock()
    result.scalar_one_or_none.return_value = locked
    db.execute.return_value = result

    monkeypatch.setattr("app.case_file_mutate_service.require_case_access", lambda *a, **k: None)
    monkeypatch.setattr("app.case_file_mutate_service.raise_if_files_checked_out", lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        rename_case_file(
            case_id,
            file_id,
            CaseFileRenameUpdate(
                original_filename="loser-name.txt",
                expected_original_filename="race.txt",
            ),
            user,
            db,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == _FILE_RENAME_BUSY_DETAIL
