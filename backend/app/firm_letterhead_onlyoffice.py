"""ONLYOFFICE editor config for firm letterhead and quote letterhead files."""

from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.file_storage import FILES_ROOT, ensure_files_root
from app.models import File as DbFile
from app.models import FirmSettings, User
from app.schemas import OnlyofficeEditorConfigOut

FirmLetterheadKind = Literal["letterhead", "quote_letterhead"]


def firm_letterhead_file_row(db: Session, kind: FirmLetterheadKind) -> DbFile:
    settings = db.get(FirmSettings, 1)
    if settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firm settings not found")
    file_id = settings.letterhead_file_id if kind == "letterhead" else settings.quote_letterhead_file_id
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No digital letterhead file uploaded yet.",
        )
    row = db.get(DbFile, file_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Letterhead file missing")
    return row


def resolve_firm_letterhead_file_row(db: Session, kind: str | None) -> DbFile | None:
    if kind not in ("letterhead", "quote_letterhead"):
        return None
    settings = db.get(FirmSettings, 1)
    if settings is None:
        return None
    file_id = settings.letterhead_file_id if kind == "letterhead" else settings.quote_letterhead_file_id
    if not file_id:
        return None
    return db.get(DbFile, file_id)


def build_firm_letterhead_onlyoffice_config(
    *,
    request: Request,
    response: Response,
    db: Session,
    user: User,
    kind: FirmLetterheadKind,
) -> OnlyofficeEditorConfigOut:
    import jwt as pyjwt

    from app.desktop_edit_session import acquire_file_edit_session
    from app.canary_public_url import onlyoffice_browser_public_base
    from app.feature_flags import onlyoffice_editor_customization
    from app.onlyoffice_ssrf_url import default_internal_base_for_ds, normalize_onlyoffice_ssrf_base
    from app.routers.files import _correct_file_type, _onlyoffice_types_for_file, _ONLYOFFICE_DOC_PERMISSIONS

    row = firm_letterhead_file_row(db, kind)
    secret = (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()
    ds_public = (os.getenv("ONLYOFFICE_DS_PUBLIC_URL") or "").strip().rstrip("/")
    if not secret or not ds_public:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="In-browser editing is not configured.",
        )

    sess, row = acquire_file_edit_session(db, case_id=None, file_id=row.id, user=user)

    ensure_files_root()
    src = (FILES_ROOT / row.storage_path).resolve()
    try:
        backup = Path(str(src) + ".oo_backup")
        if src.exists() and not backup.exists():
            shutil.copy2(src, backup)
    except Exception:
        pass

    types = _onlyoffice_types_for_file(row.original_filename)
    if not types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type not supported by editor.")
    doc_type, file_type = types
    file_type = _correct_file_type(file_type, src)

    internal = default_internal_base_for_ds()
    doc_explicit = (os.getenv("ONLYOFFICE_DOCUMENT_URL") or "").strip().rstrip("/")
    doc_base = (normalize_onlyoffice_ssrf_base(doc_explicit) if doc_explicit else "") or internal
    cb_url = f"{internal}/onlyoffice/callback?firm_letterhead_kind={kind}"

    fn = Path(row.original_filename).name
    enc = quote(fn, safe="")
    doc_url_for_ds = f"{doc_base}/webdav/sessions/{sess.token}/{enc}"
    _plain_base = onlyoffice_browser_public_base(request)
    doc_url_for_browser = f"{_plain_base}/webdav/sessions/{sess.token}/{enc}"

    doc_key = f"firm_{kind}_{row.version or 1}_{secrets.token_hex(6)}"
    jwt_payload: dict = {
        "documentType": doc_type,
        "document": {
            "title": fn,
            "url": doc_url_for_ds,
            "fileType": file_type,
            "key": doc_key,
            "permissions": dict(_ONLYOFFICE_DOC_PERMISSIONS),
        },
        "editorConfig": {
            "mode": "edit",
            "lang": "en-GB",
            "region": "en-GB",
            "location": "en-GB",
            "callbackUrl": cb_url,
            "user": {"id": str(user.id), "name": user.display_name or user.email, "group": "Canary"},
            "customization": onlyoffice_editor_customization(file_type=file_type),
        },
    }
    token = pyjwt.encode(jwt_payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    browser_document = dict(jwt_payload["document"])
    browser_document["url"] = doc_url_for_browser

    response.headers["Cache-Control"] = "no-store"
    return OnlyofficeEditorConfigOut(
        document_server_url=ds_public,
        token=token,
        document_type=doc_type,
        document=browser_document,
        editor_config=jwt_payload["editorConfig"],
        oo_compose_pending=False,
    )
