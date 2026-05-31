"""Public client portal (access code login, scoped folder browse/upload)."""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File as FastAPIFile, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.audit import log_event
from app.db import get_db
from app.deps import get_portal_contact
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.models import Case, Contact, File, FileCategory, FirmSettings, User
from app.portal_service import (
    contact_display_name,
    default_grant_label,
    ensure_upload_folder_allowed,
    get_grant_file,
    get_grant_for_contact,
    get_portal_access_by_code,
    grant_folder_display_name,
    grant_is_active,
    list_active_grants_for_contact,
    list_grant_files,
    normalize_access_code,
    portal_access_is_active,
    record_portal_auth_failure,
    record_portal_auth_success,
)
from app.schemas import (
    PortalAuthIn,
    PortalAuthOut,
    PortalConfigOut,
    PortalFileOut,
    PortalGrantSummaryOut,
    PortalSessionOut,
)
from app.alert_dispatch import AlertKind, dispatch_alert
from app.security import create_portal_session_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])


def _unlink_if_exists(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _safe_zip_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in (name or "").strip())
    return cleaned[:120] or "folder"


def _grant_summaries(db: Session, contact_id: uuid.UUID) -> list[PortalGrantSummaryOut]:
    grants = list_active_grants_for_contact(db, contact_id)
    out: list[PortalGrantSummaryOut] = []
    for g in grants:
        case = db.get(Case, g.case_id)
        case_title = (case.title or "").strip() if case else "Matter"
        if not case_title:
            case_title = "Matter"
        folder_label = grant_folder_display_name(g)
        out.append(
            PortalGrantSummaryOut(
                id=g.id,
                case_id=g.case_id,
                case_title=case_title,
                folder_path=g.folder_path or "",
                folder_label=folder_label,
                label=default_grant_label(db, g),
                can_download=g.can_download,
                can_upload=g.can_upload,
            )
        )
    return out


@router.get("/config", response_model=PortalConfigOut)
def portal_config(db: Session = Depends(get_db)) -> PortalConfigOut:
    firm = db.get(FirmSettings, 1)
    name = (firm.trading_name or "").strip() if firm else ""
    if not name and firm and firm.registered_company_name:
        name = (firm.registered_company_name or "").strip()
    return PortalConfigOut(firm_name=name or "Client portal")


@router.post("/auth", response_model=PortalAuthOut)
def portal_auth(payload: PortalAuthIn, db: Session = Depends(get_db)) -> PortalAuthOut:
    code = normalize_access_code(payload.access_code)
    if len(code) < 8:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    row = get_portal_access_by_code(db, code)
    if row is None or not portal_access_is_active(row):
        if row is not None:
            record_portal_auth_failure(db, row)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    contact = db.get(Contact, row.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    grants = list_active_grants_for_contact(db, contact.id)
    if not grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No document areas are available for this access code")
    record_portal_auth_success(db, row)
    token = create_portal_session_token(contact_id=str(contact.id))
    log_event(
        db,
        actor_user_id=None,
        action="portal.auth.success",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"contact_id": str(contact.id)},
    )
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
    )


@router.get("/session", response_model=PortalSessionOut)
def portal_session(contact: Contact = Depends(get_portal_contact), db: Session = Depends(get_db)) -> PortalSessionOut:
    grants = list_active_grants_for_contact(db, contact.id)
    if not grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No document areas are available")
    return PortalSessionOut(contact_name=contact_display_name(contact), grants=_grant_summaries(db, contact.id))


@router.get("/grants/{grant_id}/files", response_model=list[PortalFileOut])
def portal_list_files(
    grant_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> list[PortalFileOut]:
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    rows = list_grant_files(db, grant)
    return [
        PortalFileOut(
            id=f.id,
            original_filename=f.original_filename,
            mime_type=f.mime_type,
            size_bytes=f.size_bytes,
            folder_path=f.folder_path or "",
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in rows
    ]


@router.get("/grants/{grant_id}/files/download-zip")
def portal_download_grant_zip(
    grant_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
):
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    rows = list_grant_files(db, grant)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No files to download")
    ensure_files_root()
    zip_label = _safe_zip_name(grant_folder_display_name(grant))
    arc_taken: set[str] = set()
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for row in rows:
                abs_path = (FILES_ROOT / row.storage_path).resolve()
                if not str(abs_path).startswith(str(FILES_ROOT)) or not abs_path.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File missing on disk: {row.original_filename}",
                    )
                arc = _safe_zip_name(row.original_filename)
                base, ext = os.path.splitext(arc)
                n = 2
                while arc in arc_taken:
                    arc = f"{base}_{n}{ext}"
                    n += 1
                arc_taken.add(arc)
                zf.write(abs_path, arcname=arc)
        log_event(
            db,
            actor_user_id=None,
            action="portal.folder.download_zip",
            entity_type="contact_portal_grant",
            entity_id=str(grant.id),
            meta={"contact_id": str(contact.id), "case_id": str(grant.case_id), "file_count": len(rows)},
        )
        return FileResponse(
            path=tmp,
            media_type="application/zip",
            filename=f"{zip_label}.zip",
            content_disposition_type="attachment",
            background=BackgroundTask(_unlink_if_exists, tmp),
        )
    except HTTPException:
        if tmp:
            _unlink_if_exists(tmp)
        raise
    except Exception:
        if tmp:
            _unlink_if_exists(tmp)
        raise


@router.get("/grants/{grant_id}/files/{file_id}")
def portal_download_file(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    download: bool = Query(default=False),
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
):
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    row = get_grant_file(db, grant, file_id)
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not str(abs_path).startswith(str(FILES_ROOT)) or not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    log_event(
        db,
        actor_user_id=None,
        action="portal.file.download" if download else "portal.file.open",
        entity_type="file",
        entity_id=str(row.id),
        meta={"contact_id": str(contact.id), "grant_id": str(grant.id), "case_id": str(grant.case_id)},
    )
    return FileResponse(
        path=str(abs_path),
        media_type=row.mime_type,
        filename=row.original_filename,
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/grants/{grant_id}/files", response_model=PortalFileOut, status_code=status.HTTP_201_CREATED)
def portal_upload_file(
    grant_id: uuid.UUID,
    upload: UploadFile = FastAPIFile(...),
    folder: str = Form(default=""),
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalFileOut:
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    target_folder = ensure_upload_folder_allowed(grant=grant, folder=folder or grant.folder_path or "")
    case = db.get(Case, grant.case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    owner = db.get(User, case.fee_earner_user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Matter fee earner missing")

    ensure_files_root()
    file_id = uuid.uuid4()
    original = upload.filename or "upload.bin"
    paths = case_file_paths(
        case_id=grant.case_id,
        file_id=file_id,
        original_filename=original,
        folder_path=target_folder,
    )
    size = 0
    with paths.abs_path.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            f.write(chunk)

    mime = upload.content_type or (mimetypes.guess_type(original)[0] or "application/octet-stream")
    row = File(
        id=file_id,
        case_id=grant.case_id,
        owner_id=owner.id,
        category=FileCategory.case_document,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        is_pinned=False,
        original_filename=Path(original).name,
        mime_type=mime,
        size_bytes=size,
        version=1,
        checksum=None,
        parent_file_id=None,
        uploaded_via_portal=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_event(
        db,
        actor_user_id=None,
        action="portal.file.upload",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "contact_id": str(contact.id),
            "grant_id": str(grant.id),
            "case_id": str(grant.case_id),
            "folder_path": row.folder_path,
            "filename": row.original_filename,
        },
    )
    if owner.email:
        area = default_grant_label(db, grant)
        dispatch_alert(
            db,
            AlertKind.portal_staff_upload,
            to_email=owner.email,
            context={
                "contact_name": contact_display_name(contact),
                "area_label": area,
                "filename": row.original_filename,
            },
        )
    return PortalFileOut(
        id=row.id,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        folder_path=row.folder_path or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
