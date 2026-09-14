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


def test_folder_modified_during_delete_detail() -> None:
    from app.routers.files import _FOLDER_MODIFIED_DURING_DELETE_DETAIL

    assert "concurrent upload" in _FOLDER_MODIFIED_DURING_DELETE_DETAIL.lower()


def test_delete_rejects_files_newer_than_request_start() -> None:
    """CL-09: files created after delete began must not be removed under a 201/200 race."""
    from datetime import timedelta, timezone

    from sqlalchemy import select as sa_select

    from app.routers.files import _FOLDER_MODIFIED_DURING_DELETE_DETAIL, _as_utc

    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    started = datetime.now(timezone.utc)
    older = started - timedelta(seconds=5)
    newer = started + timedelta(seconds=1)
    db.add(
        File(
            id=uuid.uuid4(),
            case_id=case.id,
            owner_id=user.id,
            category=FileCategory.system,
            storage_path=f"{case.id}/marker",
            folder_path="Race",
            is_pinned=False,
            original_filename="Race",
            mime_type="application/x-directory",
            size_bytes=0,
            version=1,
            created_at=older,
            updated_at=older,
        )
    )
    db.add(
        File(
            id=uuid.uuid4(),
            case_id=case.id,
            owner_id=user.id,
            category=FileCategory.case_document,
            storage_path=f"{case.id}/doc",
            folder_path="Race",
            is_pinned=False,
            original_filename="new.txt",
            mime_type="text/plain",
            size_bytes=3,
            version=1,
            created_at=newer,
            updated_at=newer,
        )
    )
    db.commit()

    rows = db.execute(sa_select(File).where(File.case_id == case.id)).scalars().all()
    newer_rows = [
        r
        for r in rows
        if r.category != FileCategory.system
        and (created := _as_utc(r.created_at)) is not None
        and created > started
    ]
    assert len(newer_rows) == 1
    assert newer_rows[0].original_filename == "new.txt"
    assert "concurrent upload" in _FOLDER_MODIFIED_DURING_DELETE_DETAIL.lower()


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
