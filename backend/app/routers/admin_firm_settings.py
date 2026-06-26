"""Singleton firm settings: trading name, UK address, digital letterhead (.docx)."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.audit import log_event
from app.auth_principal import AuthPrincipal
from app.db import get_db
from app.deps import require_firm_admin, require_recovery_operator
from app.file_storage import (
    FILES_ROOT,
    ensure_files_root,
    firm_letterhead_file_paths,
    firm_quote_letterhead_file_paths,
)
from app.firm_letterhead_onlyoffice import (
    FirmLetterheadKind,
    build_firm_letterhead_onlyoffice_config,
    firm_letterhead_file_row,
)
from app.models import File as DbFile
from app.models import FileCategory, FirmSettings, LetterheadStyle, User
from app.onlyoffice_force_save import (
    OoForceSavePhase,
    oo_force_save_arm,
    oo_force_save_command_service,
    oo_force_save_issue_command,
    oo_force_save_wait,
)
from app.routers.onlyoffice import persist_onlyoffice_browser_url_to_file
from app.schemas import FirmSettingsOut, FirmSettingsUpdate, OnlyofficeEditorConfigOut, OoPersistDownloadIn

router = APIRouter(prefix="/admin/firm-settings", tags=["admin-firm-settings"])

log = logging.getLogger(__name__)

_MASTER_PATCH_KEYS = frozenset(
    {
        "mandate_two_factor",
        "mandate_password_rotation",
        "password_rotation_days",
    }
)

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
    quote_name: str | None = None
    if row.letterhead_file_id:
        f = db.get(DbFile, row.letterhead_file_id)
        if f:
            name = f.original_filename
    if row.quote_letterhead_file_id:
        qf = db.get(DbFile, row.quote_letterhead_file_id)
        if qf:
            quote_name = qf.original_filename
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
        quote_letterhead_style=row.quote_letterhead_style,
        quote_letterhead_original_filename=quote_name,
        mandate_two_factor=bool(row.mandate_two_factor),
        mandate_password_rotation=bool(row.mandate_password_rotation),
        password_rotation_days=row.password_rotation_days,
        client_bank_account_name=row.client_bank_account_name,
        client_bank_sort_code=row.client_bank_sort_code,
        client_bank_account_number_last4=row.client_bank_account_number_last4,
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


def _delete_quote_letterhead_file(db: Session, settings: FirmSettings) -> None:
    fid = settings.quote_letterhead_file_id
    if not fid:
        return
    f = db.get(DbFile, fid)
    settings.quote_letterhead_file_id = None
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
def get_firm_settings(
    _operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> FirmSettingsOut:
    return _to_out(db, _settings_row(db))


@router.patch("", response_model=FirmSettingsOut)
def patch_firm_settings(
    payload: FirmSettingsUpdate,
    operator: AuthPrincipal = Depends(require_recovery_operator),
    db: Session = Depends(get_db),
) -> FirmSettingsOut:
    row = _settings_row(db)
    data = payload.model_dump(exclude_unset=True)
    if operator.is_master_recovery:
        extra = set(data.keys()) - _MASTER_PATCH_KEYS
        if extra:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Master recovery may only change organisation security policy fields.",
            )
    if data.get("mandate_password_rotation") and not data.get("password_rotation_days"):
        if row.password_rotation_days is None and payload.password_rotation_days is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose how often users must update their password (rotation interval in days).",
            )
    if data.get("mandate_password_rotation") is False:
        data["password_rotation_days"] = None
    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    if operator.is_master_recovery:
        log.info("Master recovery updated firm security settings: %s", sorted(data.keys()))
    log_event(
        db,
        actor_user_id=operator.actor_user_id,
        action="firm_settings.update",
        entity_type="firm_settings",
        entity_id="1",
        meta={"keys": list(data.keys())},
    )
    return _to_out(db, row)


@router.post("/letterhead", response_model=FirmSettingsOut)
async def upload_letterhead(
    upload: UploadFile = File(...),
    admin: User = Depends(require_firm_admin),
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
def delete_letterhead(admin: User = Depends(require_firm_admin), db: Session = Depends(get_db)) -> FirmSettingsOut:
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


@router.post("/quote-letterhead", response_model=FirmSettingsOut)
async def upload_quote_letterhead(
    upload: UploadFile = File(...),
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> FirmSettingsOut:
    original = upload.filename or "quote_letterhead.bin"
    _validate_docx_upload(original, upload.content_type)

    row = _settings_row(db)
    ensure_files_root()
    _delete_quote_letterhead_file(db, row)

    file_id = uuid.uuid4()
    paths = firm_quote_letterhead_file_paths(file_id=file_id, original_filename=original)

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
    row.quote_letterhead_file_id = file_id
    row.quote_letterhead_style = LetterheadStyle.digital
    row.updated_at = now
    db.add(frow)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=admin.id,
        action="firm_settings.quote_letterhead_upload",
        entity_type="firm_settings",
        entity_id="1",
        meta={"file_id": str(file_id)},
    )
    return _to_out(db, row)


@router.delete("/quote-letterhead", response_model=FirmSettingsOut)
def delete_quote_letterhead(admin: User = Depends(require_firm_admin), db: Session = Depends(get_db)) -> FirmSettingsOut:
    row = _settings_row(db)
    _delete_quote_letterhead_file(db, row)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=admin.id,
        action="firm_settings.quote_letterhead_delete",
        entity_type="firm_settings",
        entity_id="1",
        meta={},
    )
    return _to_out(db, row)


def _firm_letterhead_onlyoffice_config(
    kind: FirmLetterheadKind,
    request: Request,
    response: Response,
    admin: User,
    db: Session,
) -> OnlyofficeEditorConfigOut:
    return build_firm_letterhead_onlyoffice_config(
        request=request,
        response=response,
        db=db,
        user=admin,
        kind=kind,
    )


async def _firm_letterhead_oo_force_save(
    kind: FirmLetterheadKind,
    doc_key: str,
    phase: OoForceSavePhase,
    base_version: int | None,
    admin: User,
    db: Session,
):
    row = firm_letterhead_file_row(db, kind)
    if phase == "arm":
        return JSONResponse({"base_version": oo_force_save_arm(db, row)})
    if phase == "wait":
        if base_version is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_version is required when phase=wait",
            )
        await oo_force_save_wait(db, row, base_version=base_version)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if phase == "command":
        await oo_force_save_issue_command(db, row, doc_key=doc_key, file_id=row.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if phase == "command_wait":
        await oo_force_save_command_service(db, row, doc_key=doc_key, file_id=row.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown phase: {phase}")


async def _firm_letterhead_oo_persist_download(
    kind: FirmLetterheadKind,
    body: OoPersistDownloadIn,
    admin: User,
    db: Session,
) -> None:
    row = firm_letterhead_file_row(db, kind)
    await persist_onlyoffice_browser_url_to_file(
        db,
        row,
        browser_url=body.browser_url,
        case_id=None,
        precedent_id=None,
        firm_letterhead_kind=kind,
    )


def _firm_letterhead_oo_save_status(
    kind: FirmLetterheadKind,
    base_version: int,
    admin: User,
    db: Session,
) -> dict[str, int | bool]:
    row = firm_letterhead_file_row(db, kind)
    version = row.version or 1
    return {"saved": version > base_version, "version": version}


@router.get("/letterhead/onlyoffice-config", response_model=OnlyofficeEditorConfigOut)
def get_letterhead_onlyoffice_config(
    request: Request,
    response: Response,
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> OnlyofficeEditorConfigOut:
    return _firm_letterhead_onlyoffice_config("letterhead", request, response, admin, db)


@router.get("/quote-letterhead/onlyoffice-config", response_model=OnlyofficeEditorConfigOut)
def get_quote_letterhead_onlyoffice_config(
    request: Request,
    response: Response,
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> OnlyofficeEditorConfigOut:
    return _firm_letterhead_onlyoffice_config("quote_letterhead", request, response, admin, db)


@router.post("/letterhead/oo-force-save")
async def oo_force_save_letterhead(
    doc_key: str,
    phase: OoForceSavePhase = Query("command"),
    base_version: int | None = Query(None),
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    return await _firm_letterhead_oo_force_save("letterhead", doc_key, phase, base_version, admin, db)


@router.post("/quote-letterhead/oo-force-save")
async def oo_force_save_quote_letterhead(
    doc_key: str,
    phase: OoForceSavePhase = Query("command"),
    base_version: int | None = Query(None),
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    return await _firm_letterhead_oo_force_save("quote_letterhead", doc_key, phase, base_version, admin, db)


@router.post("/letterhead/oo-persist-download", status_code=status.HTTP_204_NO_CONTENT)
async def oo_persist_download_letterhead(
    body: OoPersistDownloadIn,
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> None:
    await _firm_letterhead_oo_persist_download("letterhead", body, admin, db)


@router.post("/quote-letterhead/oo-persist-download", status_code=status.HTTP_204_NO_CONTENT)
async def oo_persist_download_quote_letterhead(
    body: OoPersistDownloadIn,
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> None:
    await _firm_letterhead_oo_persist_download("quote_letterhead", body, admin, db)


@router.get("/letterhead/oo-save-status")
def oo_save_status_letterhead(
    base_version: int = Query(...),
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> dict[str, int | bool]:
    return _firm_letterhead_oo_save_status("letterhead", base_version, admin, db)


@router.get("/quote-letterhead/oo-save-status")
def oo_save_status_quote_letterhead(
    base_version: int = Query(...),
    admin: User = Depends(require_firm_admin),
    db: Session = Depends(get_db),
) -> dict[str, int | bool]:
    return _firm_letterhead_oo_save_status("quote_letterhead", base_version, admin, db)
