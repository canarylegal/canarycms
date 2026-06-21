"""Generate immutable PDF snapshots for portal quote deliveries."""

from __future__ import annotations

import logging
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
import jwt
from sqlalchemy.orm import Session

from app.desktop_edit_session import acquire_file_edit_session
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.models import File, FileCategory, QuotePortalDelivery, User
from app.onlyoffice_ssrf_url import default_internal_base_for_ds
from app.routers.onlyoffice import _rewrite_oo_download_url

log = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"
_OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
_CONVERT_MAX_BYTES = int(os.getenv("PORTAL_QUOTE_PDF_MAX_BYTES", str(50 * 1024 * 1024)))


def _onlyoffice_jwt_secret() -> str:
    return (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()


def _onlyoffice_ds_internal_url() -> str:
    return (os.getenv("ONLYOFFICE_DS_INTERNAL_URL") or "http://onlyoffice").strip().rstrip("/")


def _office_filetype(original_filename: str) -> str:
    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext == "doc":
        return "doc"
    if ext in ("xls", "csv"):
        return "xls"
    if ext == "ppt":
        return "ppt"
    return ext or "docx"


def _parse_onlyoffice_convert_response(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    if not text:
        raise RuntimeError("ONLYOFFICE conversion returned an empty response")
    if text.startswith("{"):
        import json

        data = json.loads(text)
        if not isinstance(data, dict):
            raise RuntimeError("ONLYOFFICE conversion returned an invalid response")
        return {str(k): str(v) for k, v in data.items() if v is not None}

    root = ET.fromstring(text)
    out: dict[str, str] = {}
    for child in root:
        if child.text is not None:
            out[child.tag] = child.text.strip()
    return out


def convert_case_file_to_pdf_bytes_via_onlyoffice(
    db: Session,
    *,
    source: File,
    user: User,
    conversion_key: str,
) -> bytes:
    """Convert a case document to PDF using ONLYOFFICE Document Server."""
    if not _onlyoffice_jwt_secret():
        raise RuntimeError("ONLYOFFICE is not configured for portal quote PDF conversion")

    sess, row = acquire_file_edit_session(
        db,
        case_id=source.case_id,
        file_id=source.id,
        user=user,
    )
    base = default_internal_base_for_ds()
    fn = Path(row.original_filename).name
    doc_url = f"{base}/webdav/sessions/{sess.token}/{quote(fn, safe='')}"
    payload = {
        "async": False,
        "filetype": _office_filetype(fn),
        "key": conversion_key,
        "outputtype": "pdf",
        "title": fn,
        "url": doc_url,
    }
    secret = _onlyoffice_jwt_secret()
    body: dict[str, object] = {"token": jwt.encode(payload, secret, algorithm="HS256")}

    convert_url = f"{_onlyoffice_ds_internal_url()}/ConvertService.ashx"
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(convert_url, json=body)
        resp.raise_for_status()
        data = _parse_onlyoffice_convert_response(resp.text)
        if data.get("Error"):
            raise RuntimeError(f"ONLYOFFICE conversion failed: {data.get('Error')}")
        end_convert = (data.get("EndConvert") or data.get("endConvert") or "").lower()
        if end_convert not in ("true", "1"):
            raise RuntimeError("ONLYOFFICE conversion did not complete")
        file_url = data.get("FileUrl") or data.get("fileUrl")
        if not isinstance(file_url, str) or not file_url.strip():
            raise RuntimeError("ONLYOFFICE conversion returned no PDF URL")

        fetch_url = _rewrite_oo_download_url(file_url.strip())
        pdf_resp = client.get(fetch_url)
        pdf_resp.raise_for_status()
        pdf_bytes = pdf_resp.content

    if not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError("ONLYOFFICE conversion did not return a valid PDF")
    if len(pdf_bytes) > _CONVERT_MAX_BYTES:
        raise RuntimeError("Converted PDF exceeds size limit")
    return pdf_bytes


def portal_quote_pdf_filename(source: File) -> str:
    stem = Path(source.original_filename).stem.strip() or "Quote"
    return f"{stem}.pdf"


def _read_source_bytes(
    db: Session,
    *,
    source: File,
    delivery: QuotePortalDelivery,
    owner_user_id: uuid.UUID,
) -> tuple[bytes, str]:
    ensure_files_root()
    abs_path = (FILES_ROOT / source.storage_path).resolve()
    if not str(abs_path).startswith(str(FILES_ROOT)) or not abs_path.is_file():
        raise FileNotFoundError("Quote source file missing on disk")

    ext = Path(source.original_filename).suffix.lower()
    mime = (source.mime_type or "").strip().lower()
    pdf_name = portal_quote_pdf_filename(source)
    if mime == _PDF_MIME or ext == ".pdf":
        return abs_path.read_bytes(), pdf_name

    if ext not in _OFFICE_EXTS:
        raise RuntimeError(f"Unsupported quote format for portal PDF: {source.original_filename}")

    if not _onlyoffice_jwt_secret():
        raise RuntimeError("ONLYOFFICE is not configured for portal quote PDF conversion")

    user = db.get(User, owner_user_id)
    if user is None:
        raise RuntimeError("Quote sender user not found")

    return (
        convert_case_file_to_pdf_bytes_via_onlyoffice(
            db,
            source=source,
            user=user,
            conversion_key=f"portal-quote-{delivery.id}",
        ),
        pdf_name,
    )


def create_portal_quote_pdf_snapshot(
    db: Session,
    *,
    source: File,
    delivery: QuotePortalDelivery,
    owner_user_id: uuid.UUID,
) -> File | None:
    """Create a system-scoped PDF snapshot linked to a quote delivery."""
    try:
        pdf_bytes, pdf_name = _read_source_bytes(
            db,
            source=source,
            delivery=delivery,
            owner_user_id=owner_user_id,
        )
    except Exception:
        log.exception(
            "portal quote PDF snapshot failed delivery=%s source=%s",
            delivery.id,
            source.id,
        )
        return None

    new_id = uuid.uuid4()
    paths = case_file_paths(
        case_id=delivery.case_id,
        file_id=new_id,
        original_filename=pdf_name,
        folder_path=source.folder_path or "",
    )
    paths.abs_path.write_bytes(pdf_bytes)

    now = datetime.now(timezone.utc)
    row = File(
        id=new_id,
        case_id=delivery.case_id,
        owner_id=owner_user_id,
        category=FileCategory.system,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        parent_file_id=source.id,
        original_filename=pdf_name,
        mime_type=_PDF_MIME,
        size_bytes=len(pdf_bytes),
        version=1,
        checksum=None,
        is_portal_quote=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    delivery.portal_pdf_file_id = row.id
    db.add(delivery)
    db.flush()
    log.info(
        "portal quote PDF snapshot delivery=%s source=%s pdf=%s bytes=%s",
        delivery.id,
        source.id,
        row.id,
        len(pdf_bytes),
    )
    return row
