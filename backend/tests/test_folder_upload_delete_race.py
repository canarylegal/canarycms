"""CL-09 folder destination checks for upload-vs-delete races."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models import File, FileCategory
from app.routers.files import (
    _FILE_RENAME_CONFLICT_DETAIL,
    _FOLDER_GONE_DETAIL,
    _folder_destination_exists,
    _prepare_upload_folder,
)
from tests.ledger_test_helpers import add_case, add_user, ledger_test_session


def test_file_rename_conflict_detail_constant() -> None:
    assert "renamed or moved" in _FILE_RENAME_CONFLICT_DETAIL.lower()


def test_session_folder_lock_helpers_noop_on_sqlite() -> None:
    from app.routers.files import _try_lock_case_folder_ops_session, _unlock_case_folder_ops_session

    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    assert _try_lock_case_folder_ops_session(db, case.id) is True
    _unlock_case_folder_ops_session(db, case.id)


def test_folder_destination_exists_root_always() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    assert _folder_destination_exists(db, case.id, "") is True


def test_folder_destination_missing_without_marker() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    assert _folder_destination_exists(db, case.id, "Gone") is False


def test_folder_destination_exists_with_marker() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    db.add(
        File(
            id=uuid.uuid4(),
            case_id=case.id,
            owner_id=user.id,
            category=FileCategory.system,
            storage_path=f"{case.id}/x",
            folder_path="Docs",
            is_pinned=False,
            original_filename="Docs",
            mime_type="application/x-directory",
            size_bytes=0,
            version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    assert _folder_destination_exists(db, case.id, "Docs") is True


def test_prepare_upload_folder_rejects_missing_destination() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    with pytest.raises(HTTPException) as exc:
        _prepare_upload_folder(db, case.id, "Missing")
    assert exc.value.status_code == 409
    assert exc.value.detail == _FOLDER_GONE_DETAIL


def test_prepare_upload_folder_allows_root() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    assert _prepare_upload_folder(db, case.id, "") == ""
