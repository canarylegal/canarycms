"""Singleton firm settings: trading name, UK address, digital letterhead (.docx)."""

from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import require_admin
from app.file_storage import FILES_ROOT, ensure_files_root, firm_letterhead_file_paths
from app.models import File as DbFile
from app.models import FileCategory, FirmSettings, LetterheadStyle, User
from app.schemas import FirmSettingsOut, FirmSettingsUpdate

router = APIRouter(prefix="/admin/firm-settings", tags=["admin-firm-settings"])

_ALLOWED_LETTERHEAD_SUFFIX = frozenset({".docx"})
_ALLOWED_LETTERHEAD_MIME = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


def _settings_row(db: Session) -> FirmSettings:
    row = db.get(FirmSettings, 1)
    if row is None:
        row = FirmSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _to_out(db: Session, row: FirmSettings) -> FirmSettingsOut:
    name: str | None = None
    if row.letterhead_file_id:
        f = db.get(DbFile, row.letterhead_file_id)
        if f:
            name = f.original_filename
    return FirmSettingsOut(
        id=row.id,
        trading_name=row.trading_name or "",
        registered_company_name=row.registered_company_name,
        addr_line1=row.addr_line1,
        addr_line2=row.addr_line2,
        town_city=row.town_city,
        county=row.county,
        postcode=row.postcode,
        letterhead_style=row.letterhead_style,
        letterhead_original_filename=name,
        mandate_two_factor=bool(row.mandate_two_factor),
    )


def _validate_docx_upload(filename: str, content_type: str | None) -> None:
    suf = Path(filename or "").suffix.lower()
    if suf not in _ALLOWED_LETTERHEAD_SUFFIX:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Digital letterhead must be a .docx file.",
        )
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime and mime not in _ALLOWED_LETTERHEAD_MIME:
        guess = mimetypes.guess_type(filename)[0]
        if guess not in _ALLOWED_LETTERHEAD_MIME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Digital letterhead must be Word OOXML (.docx).",
            )


def _delete_letterhead_file(db: Session, settings: FirmSettings) -> None:
    fid = settings.letterhead_file_id
    if not fid:
        return
    f = db.get(DbFile, fid)
    settings.letterhead_file_id = None
    if f:
        abs_path = (FILES_ROOT / f.storage_path).resolve()
        db.delete(f)
        db.flush()
        if str(abs_path).startswith(str(FILES_ROOT)) and abs_path.is_file():
            try:
                abs_path.unlink()
            except OSError:
                pass


@router.get("", response_model=FirmSettingsOut)
def get_firm_settings(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> FirmSettingsOut:
    return _to_out(db, _settings_row(db))


@router.patch("", response_model=FirmSettingsOut)
def patch_firm_settings(
    payload: FirmSettingsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FirmSettingsOut:
    row = _settings_row(db)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=admin.id,
        action="firm_settings.update",
        entity_type="firm_settings",
        entity_id="1",
        meta={"keys": list(data.keys())},
    )
    return _to_out(db, row)


@router.post("/letterhead", response_model=FirmSettingsOut)
async def upload_letterhead(
    upload: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FirmSettingsOut:
    original = upload.filename or "letterhead.bin"
    _validate_docx_upload(original, upload.content_type)

    row = _settings_row(db)
    ensure_files_root()
    _delete_letterhead_file(db, row)

    file_id = uuid.uuid4()
    paths = firm_letterhead_file_paths(file_id=file_id, original_filename=original)

    size = 0
    with paths.abs_path.open("wb") as fh:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            fh.write(chunk)

    mime = upload.content_type or (
        mimetypes.guess_type(original)[0]
        or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    if mime.split(";", 1)[0].strip().lower() not in _ALLOWED_LETTERHEAD_MIME:
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    now = datetime.utcnow()
    frow = DbFile(
        id=file_id,
        case_id=None,
        owner_id=admin.id,
        category=FileCategory.firm_letterhead,
        storage_path=paths.rel_path,
        folder_path="",
        parent_file_id=None,
        is_pinned=False,
        original_filename=Path(original).name,
        mime_type=mime,
        size_bytes=size,
        version=1,
        checksum=None,
        created_at=now,
        updated_at=now,
    )
    row.letterhead_file_id = file_id
    row.letterhead_style = LetterheadStyle.digital
    row.updated_at = now
    db.add(frow)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=admin.id,
        action="firm_settings.letterhead_upload",
        entity_type="firm_settings",
        entity_id="1",
        meta={"file_id": str(file_id)},
    )
    return _to_out(db, row)


@router.delete("/letterhead", response_model=FirmSettingsOut)
def delete_letterhead(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> FirmSettingsOut:
    row = _settings_row(db)
    _delete_letterhead_file(db, row)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=admin.id,
        action="firm_settings.letterhead_delete",
        entity_type="firm_settings",
        entity_id="1",
        meta={},
    )
    return _to_out(db, row)
