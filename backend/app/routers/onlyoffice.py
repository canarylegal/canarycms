"""
ONLYOFFICE Document Server callback (save). Document URL uses the same WebDAV session token as checkout.

Canary print staging: ``downloadAs('pdf')`` and native print both yield DS URLs under ``/cache/files/…``
or ``/printfile/…``. The backend fetches those only on the internal DS base (SSRF-safe); the SPA
``/oo-print`` route loads PDF.js and ``window.print()`` using staged bytes from ``/onlyoffice/print-staged-pdf``
so Firefox does not hand off ``application/pdf`` to the global PDF handler.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.models import FeeScale, File as DbFile, FileCategory, FileEditSession, Precedent, User
from app.audit import log_event
from app.feature_flags import onlyoffice_callback_require_jwt
from app.docx_util import finalize_stored_docx_bytes, normalize_onlyoffice_persisted_docx_bytes

router = APIRouter(prefix="/onlyoffice", tags=["onlyoffice"])
log = logging.getLogger(__name__)

# Docker service names that are already reachable from the backend container.
_OO_INTERNAL_HOSTS = {"onlyoffice", "canary-onlyoffice"}


def _strip_ds_reverse_proxy_prefix(path: str) -> str:
    """Strip the public site path prefix where DS is mounted (e.g. /office-ds).

    Callback URLs often look like ``https://app/office-ds/cache/...``. The Document Server
    container serves ``/cache/...`` at its HTTP root, not ``/office-ds/cache/...``, so the
    backend must fetch ``http://onlyoffice/cache/...`` — not ``http://onlyoffice/office-ds/...``
    (which returns 404).

    Override with env ``ONLYOFFICE_DS_PATH_PREFIX_STRIP`` (default ``/office-ds``). Set the
    variable to an empty string to disable stripping.
    """
    env_val = os.getenv("ONLYOFFICE_DS_PATH_PREFIX_STRIP")
    if env_val is not None and env_val.strip() == "":
        return path
    raw = (env_val if env_val is not None else "/office-ds").strip()
    if not raw or raw == "/":
        return path
    prefix = raw.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    if p == prefix:
        return "/"
    if p.startswith(prefix + "/"):
        return p[len(prefix) :] or "/"
    return p


def _rewrite_oo_download_url(url: str) -> str:
    """Rewrite the OO DS download URL so the backend container can reach it.

    OO DS embeds the browser's X-Forwarded-Host (e.g. localhost:5173) in its callback payload.
    That URL works from the user's browser but not from inside the backend Docker container.
    Rewrite non-Docker hosts to the OO DS internal URL (default: http://onlyoffice).

    Also strips the reverse-proxy path prefix (``/office-ds``) so internal fetches hit DS paths
    the container actually serves.
    """
    oo_internal = (os.getenv("ONLYOFFICE_DS_INTERNAL_URL") or "http://onlyoffice").strip().rstrip("/")
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        int_host = (urlparse(oo_internal).hostname or "onlyoffice").lower()
        known = _OO_INTERNAL_HOSTS | {int_host}
        path_norm = _strip_ds_reverse_proxy_prefix(p.path or "/")

        if host in known:
            out = urlunparse((p.scheme, p.netloc, path_norm, p.params, p.query, p.fragment))
            if out != url:
                log.info("_rewrite_oo_download_url (internal host): %s → %s", url, out)
            return out

        base = urlparse(oo_internal)
        rewritten = urlunparse(
            (
                base.scheme or "http",
                base.netloc or "onlyoffice",
                path_norm,
                p.params,
                p.query,
                p.fragment,
            )
        )
        log.info("_rewrite_oo_download_url: %s → %s", url, rewritten)
        return rewritten
    except Exception as exc:
        log.warning("_rewrite_oo_download_url failed for %r: %s", url, exc)
        return url


def _onlyoffice_jwt_secret() -> str:
    return (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()


def _decode_callback_payload(request: Request, body: Any) -> dict[str, Any]:
    secret = _onlyoffice_jwt_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ONLYOFFICE JWT secret is not configured",
        )
    if isinstance(body, str):
        try:
            return jwt.decode(body, secret, algorithms=["HS256"], options={"verify_aud": False})
        except JWTError as e:
            log.warning("ONLYOFFICE callback JWT (raw body) failed: %s", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        try:
            return jwt.decode(auth[7:], secret, algorithms=["HS256"], options={"verify_aud": False})
        except JWTError:
            pass

    if isinstance(body, dict) and "token" in body:
        try:
            return jwt.decode(
                body["token"],
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except JWTError as e:
            log.warning("ONLYOFFICE callback JWT failed: %s", e)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # OO DS 7.5 does not include an outbox JWT in callbacks despite local.json configuration.
    # Accept plain callbacks when the body contains the expected OO DS fields (key + status),
    # unless ONLYOFFICE_CALLBACK_REQUIRE_JWT=1 (recommended for production / DS 8+).
    if isinstance(body, dict) and "status" in body and "key" in body:
        if onlyoffice_callback_require_jwt():
            log.warning(
                "onlyoffice_callback: unsigned payload rejected (ONLYOFFICE_CALLBACK_REQUIRE_JWT=1; key=%s status=%s)",
                body.get("key"),
                body.get("status"),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ONLYOFFICE callback JWT required",
            )
        log.warning(
            "onlyoffice_callback: no JWT in callback body — accepting plain payload "
            "(OO DS outbox JWT not sent by this version; key=%s status=%s)",
            body.get("key"),
            body.get("status"),
        )
        return body

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid JWT")


_PRINT_STAGING_TTL_SECONDS = int(os.getenv("ONLYOFFICE_PRINT_STAGE_TTL_SECONDS", "900"))
_PRINT_STAGING_MAX_BYTES = int(os.getenv("ONLYOFFICE_PRINT_STAGE_MAX_BYTES", str(50 * 1024 * 1024)))
_PRINT_JWT_ALG = "HS256"
_PRINT_JWT_PURPOSE = "oo_print_staged"
_PRINT_STORE_LOCK = threading.Lock()
_PRINT_STORE: dict[str, tuple[bytes, float]] = {}


def _print_stage_secret_raw() -> str:
    return (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()


def _gc_print_store_unlocked(now: float) -> None:
    dead = [k for k, (_, exp) in _PRINT_STORE.items() if exp <= now]
    for k in dead:
        _PRINT_STORE.pop(k, None)


def _normalized_ds_path_for_print_allowlist(url: str) -> str:
    try:
        p = urlparse(url)
        return _strip_ds_reverse_proxy_prefix(p.path or "/")
    except Exception:
        return ""


def _is_allowed_onlyoffice_ds_fetch_path(path: str) -> bool:
    if not path.startswith("/"):
        path = "/" + path
    parts: list[str] = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            else:
                return False
        else:
            parts.append(seg)
    norm = "/" + "/".join(parts)
    return norm.startswith("/printfile/") or norm.startswith("/cache/files/")


def _internal_fetch_url_from_browser(browser_url: str) -> str:
    u = browser_url.strip()
    if not u or not re.match(r"^https?://", u, re.I):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="browser_url must be an http(s) URL",
        )
    rewritten = _rewrite_oo_download_url(u)
    norm_path = _normalized_ds_path_for_print_allowlist(rewritten)
    if not _is_allowed_onlyoffice_ds_fetch_path(norm_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must target ONLYOFFICE /printfile/… or /cache/files/…",
        )
    try:
        fu = urlparse(rewritten)
        if fu.scheme not in ("http", "https"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid URL scheme")
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("print-stage: bad URL %r: %s", rewritten, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid URL") from exc
    return rewritten


_OO_PERSIST_MAX_BYTES = int(os.getenv("ONLYOFFICE_PERSIST_MAX_BYTES", str(100 * 1024 * 1024)))


def fix_pdf_form_need_appearances(data: bytes) -> bytes:
    """``downloadAs`` PDFs may store field values without appearance streams.

    Set AcroForm ``/NeedAppearances`` so conforming readers (including ONLYOFFICE on reopen)
    regenerate visible field content instead of showing blanks until focus.
    """

    if not data.startswith(b"%PDF"):
        return data
    try:
        import pikepdf
    except ImportError:
        log.warning("pikepdf not installed; skipping PDF NeedAppearances fix")
        return data
    try:
        with pikepdf.open(BytesIO(data)) as pdf:
            if "/AcroForm" not in pdf.Root:
                return data
            acro = pdf.Root.AcroForm
            if acro is None:
                return data
            acro["/NeedAppearances"] = True
            out = BytesIO()
            pdf.save(out)
            return out.getvalue()
    except Exception as exc:
        log.warning("fix_pdf_form_need_appearances failed: %s", exc)
        return data


def _validate_persist_magic(data: bytes, *, filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty document")
    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Response is not a PDF")
    elif ext in (
        ".docx",
        ".docm",
        ".xlsx",
        ".xlsm",
        ".pptx",
        ".pptm",
        ".odt",
        ".ods",
        ".odp",
    ):
        if data[:2] != b"PK":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Response is not a valid Office document",
            )


async def _fetch_onlyoffice_download_bytes(browser_url: str, *, log_label: str) -> bytes:
    fetch_url = _internal_fetch_url_from_browser(browser_url)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(fetch_url)
            r.raise_for_status()
            data = r.content
    except HTTPException:
        raise
    except Exception as e:
        log.exception("%s: fetch failed url=%s", log_label, fetch_url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not fetch document from Document Server",
        ) from e
    if len(data) > _OO_PERSIST_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Document exceeds persist size limit",
        )
    return data


def allocate_pdf_export_filename(
    db: Session,
    *,
    case_id: uuid.UUID,
    folder_path: str,
    preferred: str,
) -> str:
    """Pick a unique ``.pdf`` name in the same matter folder as the source document."""

    safe = Path(preferred).name
    if not safe.lower().endswith(".pdf"):
        safe = f"{Path(safe).stem}.pdf"
    folder = folder_path or ""
    existing = {
        name
        for (name,) in db.execute(
            select(DbFile.original_filename).where(
                DbFile.case_id == case_id,
                DbFile.folder_path == folder,
                DbFile.category == FileCategory.case_document,
            )
        ).all()
        if name
    }
    if safe not in existing:
        return safe
    stem = Path(safe).stem
    n = 2
    while True:
        candidate = f"{stem} ({n}).pdf"
        if candidate not in existing:
            return candidate
        n += 1


async def create_case_file_from_onlyoffice_pdf_export(
    db: Session,
    source: DbFile,
    *,
    browser_url: str,
    case_id: uuid.UUID,
    user: User,
    filename: str | None = None,
) -> DbFile:
    """Create a new case PDF from ONLYOFFICE ``downloadAs`` (does not modify ``source``)."""

    if Path(source.original_filename).suffix.lower() == ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source document is already a PDF",
        )

    data = await _fetch_onlyoffice_download_bytes(browser_url, log_label="oo-export-pdf")
    _validate_persist_magic(data, filename="export.pdf")
    data = fix_pdf_form_need_appearances(data)

    preferred = (filename or "").strip() or f"{Path(source.original_filename).stem}.pdf"
    out_name = allocate_pdf_export_filename(
        db,
        case_id=case_id,
        folder_path=source.folder_path or "",
        preferred=preferred,
    )

    new_id = uuid.uuid4()
    paths = case_file_paths(
        case_id=case_id,
        file_id=new_id,
        original_filename=out_name,
        folder_path=source.folder_path or "",
    )
    ensure_files_root()
    paths.abs_path.write_bytes(data)

    now = datetime.now(timezone.utc)
    row = DbFile(
        id=new_id,
        case_id=case_id,
        owner_id=user.id,
        category=FileCategory.case_document,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        parent_file_id=source.id if source.is_portal_quote else None,
        source_imap_mbox=None,
        source_imap_uid=None,
        source_mail_from_name=None,
        source_mail_from_email=None,
        source_mail_is_outbound=None,
        source_internet_message_id=None,
        source_mail_date=None,
        source_outlook_conversation_id=None,
        source_outlook_item_id=None,
        outlook_graph_message_id=None,
        outlook_web_link=None,
        is_pinned=False,
        original_filename=out_name,
        mime_type="application/pdf",
        size_bytes=len(data),
        version=1,
        checksum=None,
        is_portal_quote=bool(source.is_portal_quote),
        created_at=now,
        updated_at=now,
    )
    if source.is_portal_quote:
        source.is_portal_quote = False
        source.updated_at = now
        db.add(source)
    db.add(row)
    db.commit()
    db.refresh(row)

    log.info(
        "oo-export-pdf: created file=%s from source=%s name=%s size=%s",
        row.id,
        source.id,
        out_name,
        len(data),
    )
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.export_pdf",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "case_id": str(case_id),
            "source_file_id": str(source.id),
            "filename": out_name,
            "size_bytes": len(data),
            "folder": paths.folder_path,
        },
    )
    return row


async def persist_onlyoffice_browser_url_to_file(
    db: Session,
    row: DbFile,
    *,
    browser_url: str,
    case_id: uuid.UUID | None,
    precedent_id: uuid.UUID | None,
    firm_letterhead_kind: str | None = None,
) -> int:
    """Fetch a DS ``downloadAs`` / cache URL and write bytes to Canary file storage."""

    data = await _fetch_onlyoffice_download_bytes(browser_url, log_label=f"oo-persist file={row.id}")

    _validate_persist_magic(data, filename=row.original_filename)

    if Path(row.original_filename).suffix.lower() == ".pdf":
        data = fix_pdf_form_need_appearances(data)

    data = normalize_onlyoffice_persisted_docx_bytes(
        data,
        filename=row.original_filename,
        mime_type=row.mime_type,
    )
    data = finalize_stored_docx_bytes(
        data,
        filename=row.original_filename,
        mime_type=row.mime_type,
    )

    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not str(abs_path).startswith(str(FILES_ROOT.resolve())):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid storage path")

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(data)

    backup_path = Path(str(abs_path) + ".oo_backup")
    if backup_path.exists():
        try:
            backup_path.unlink()
        except Exception as exc:
            log.warning("Could not delete backup %s: %s", backup_path, exc)

    row.version = (row.version or 1) + 1
    row.size_bytes = len(data)
    row.updated_at = datetime.now(timezone.utc)
    row.oo_force_save_pending = False
    if case_id is not None:
        from app.quote_portal_service import supersede_pending_quote_deliveries

        supersede_pending_quote_deliveries(db, row.id)
    db.add(row)
    db.commit()

    log.info(
        "oo-persist: saved file=%s version=%s size=%s",
        row.id,
        row.version,
        len(data),
    )
    action, meta_extra = _oo_save_audit_action_meta(
        precedent_id=precedent_id,
        case_id=case_id,
        firm_letterhead_kind=firm_letterhead_kind,
    )
    log_event(
        db,
        actor_user_id=None,
        action=action,
        entity_type="file",
        entity_id=str(row.id),
        meta={**meta_extra, "version": row.version, "size_bytes": len(data), "via": "downloadAs"},
    )
    return int(row.version)


def _encode_print_staging_jwt(*, sid: str) -> str:
    secret = _print_stage_secret_raw()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ONLYOFFICE JWT secret is not configured",
        )
    now = int(time.time())
    ttl = min(_PRINT_STAGING_TTL_SECONDS, 3600)
    return jwt.encode(
        {
            "purpose": _PRINT_JWT_PURPOSE,
            "sid": sid,
            "iat": now,
            "exp": now + ttl,
        },
        secret,
        algorithm=_PRINT_JWT_ALG,
    )


def _decode_print_staging_jwt(token: str) -> str:
    secret = _print_stage_secret_raw()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ONLYOFFICE JWT secret is not configured",
        )
    try:
        payload = jwt.decode(token, secret, algorithms=[_PRINT_JWT_ALG])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired print token",
        ) from e
    if payload.get("purpose") != _PRINT_JWT_PURPOSE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid print token")
    sid = payload.get("sid")
    if not isinstance(sid, str) or not sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid print token")
    return sid


class PrintStageIn(BaseModel):
    browser_url: str = Field(..., min_length=8, max_length=8000)


@router.post("/print-stage")
async def onlyoffice_print_stage(
    body: PrintStageIn,
    _user: User = Depends(get_current_user),
) -> dict[str, str]:
    fetch_url = _internal_fetch_url_from_browser(body.browser_url)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(fetch_url)
            r.raise_for_status()
            data = r.content
    except HTTPException:
        raise
    except Exception as e:
        log.exception("print-stage: fetch failed url=%s", fetch_url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not fetch PDF from Document Server",
        ) from e

    if len(data) > _PRINT_STAGING_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds staging size limit",
        )
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Response is not a PDF")

    sid = uuid.uuid4().hex
    exp = time.time() + _PRINT_STAGING_TTL_SECONDS
    with _PRINT_STORE_LOCK:
        _gc_print_store_unlocked(time.time())
        _PRINT_STORE[sid] = (data, exp)

    t = _encode_print_staging_jwt(sid=sid)
    return {"sid": sid, "t": t}


@router.get("/print-staged-pdf")
async def onlyoffice_print_staged_pdf(
    sid: str = Query(..., min_length=8, max_length=128),
    t: str = Query(..., min_length=10, max_length=4096),
) -> Response:
    jwt_sid = _decode_print_staging_jwt(t)
    if jwt_sid != sid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sid mismatch")
    with _PRINT_STORE_LOCK:
        entry = _PRINT_STORE.get(sid)
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print session expired or not found")
        data, exp = entry
        if exp <= time.time():
            _PRINT_STORE.pop(sid, None)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Print session expired")
    return Response(content=data, media_type="application/pdf")


def _callback_status_int(raw: object) -> int | None:
    """ONLYOFFICE sometimes sends numeric statuses as strings; coerce for reliable branching."""

    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _callback_download_url(payload: dict[str, Any]) -> str | None:
    u = payload.get("url")
    if isinstance(u, str):
        t = u.strip()
        return t or None
    return None


def _callback_resolve_file_row(
    db: Session,
    *,
    case_id: uuid.UUID | None,
    file_id: uuid.UUID | None,
    precedent_id: uuid.UUID | None,
    fee_scale_id: uuid.UUID | None = None,
    firm_letterhead_kind: str | None = None,
) -> DbFile | None:
    """Resolve the backing ``file`` row for a ONLYOFFICE callback (case file or precedent template)."""

    from app.firm_letterhead_onlyoffice import resolve_firm_letterhead_file_row

    if firm_letterhead_kind:
        return resolve_firm_letterhead_file_row(db, firm_letterhead_kind)
    if fee_scale_id is not None:
        scale = db.get(FeeScale, fee_scale_id)
        if not scale:
            return None
        return db.get(DbFile, scale.file_id)
    if precedent_id is not None:
        prec = db.get(Precedent, precedent_id)
        if not prec:
            return None
        return db.get(DbFile, prec.file_id)
    if case_id is None or file_id is None:
        return None
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        return None
    return row


def _oo_save_audit_action_meta(
    *,
    precedent_id: uuid.UUID | None,
    case_id: uuid.UUID | None,
    firm_letterhead_kind: str | None,
) -> tuple[str, dict[str, str]]:
    if firm_letterhead_kind in ("letterhead", "quote_letterhead"):
        return (
            f"firm_settings.{firm_letterhead_kind}_onlyoffice_save",
            {"firm_letterhead_kind": firm_letterhead_kind},
        )
    if precedent_id is not None:
        return "precedent.onlyoffice_save", {"precedent_id": str(precedent_id)}
    return "case.file.onlyoffice_save", {"case_id": str(case_id)}


def _oo_ack_unchanged_force_save(
    db: Session,
    row: DbFile,
    *,
    precedent_id: uuid.UUID | None,
    case_id: uuid.UUID | None,
    firm_letterhead_kind: str | None = None,
    status_code: int,
) -> None:
    """Complete /oo-force-save when DS omits ``url`` (document unchanged). Bump version only metadata-wise."""

    row.version = (row.version or 1) + 1
    row.updated_at = datetime.now(timezone.utc)
    row.oo_force_save_pending = False
    if case_id is not None:
        from app.quote_portal_service import supersede_pending_quote_deliveries

        supersede_pending_quote_deliveries(db, row.id)
    db.add(row)
    db.commit()
    log.info(
        "onlyoffice_callback: unchanged force-save ack file=%s callback_status=%s version=%s",
        row.id,
        status_code,
        row.version,
    )
    action, meta_extra = _oo_save_audit_action_meta(
        precedent_id=precedent_id,
        case_id=case_id,
        firm_letterhead_kind=firm_letterhead_kind,
    )
    log_event(
        db,
        actor_user_id=None,
        action=f"{action}_unchanged",
        entity_type="file",
        entity_id=str(row.id),
        meta={**meta_extra, "callback_status": status_code, "version": row.version},
    )


@router.post("/callback")
async def onlyoffice_callback(
    request: Request,
    case_id: uuid.UUID | None = Query(None),
    file_id: uuid.UUID | None = Query(None),
    precedent_id: uuid.UUID | None = Query(None),
    fee_scale_id: uuid.UUID | None = Query(None),
    firm_letterhead_kind: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if (
        precedent_id is None
        and fee_scale_id is None
        and firm_letterhead_kind is None
        and (case_id is None or file_id is None)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing case_id or file_id")

    raw = await request.body()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = raw.decode("utf-8", errors="replace").strip()

    payload = _decode_callback_payload(request, body)
    # When JWT_IN_BODY=true OO DS wraps the callback data under a nested "payload" key.
    if "payload" in payload and isinstance(payload["payload"], dict):
        payload = payload["payload"]
    st = _callback_status_int(payload.get("status"))
    download_url = _callback_download_url(payload)

    log.warning(
        "onlyoffice_callback: file_id=%s status=%s url=%r keys=%s",
        file_id, st, download_url, list(payload.keys()),
    )

    if st is None:
        log.warning("onlyoffice_callback: missing or non-numeric status — ignoring")
        return {"error": 0}

    # 7 = Document Server reported a force-save error (often seen when there is nothing new to persist).
    # Do **not** clear ``oo_force_save_pending`` here: clearing without bumping ``version`` makes
    # POST /oo-force-save wait until timeout and then return HTTP 504. ``/oo-force-save`` completes
    # with a metadata version bump when the CommandService forcesave itself succeeded.
    if st == 7:
        row7 = _callback_resolve_file_row(
            db,
            case_id=case_id,
            file_id=file_id,
            precedent_id=precedent_id,
            fee_scale_id=fee_scale_id,
            firm_letterhead_kind=firm_letterhead_kind,
        )
        if row7 is not None:
            log.warning(
                "onlyoffice_callback: force-save status=7 (DS error) file=%s oo_force_save_pending=%s",
                row7.id,
                row7.oo_force_save_pending,
            )
        return {"error": 0}

    # 2 = document closed, must save; 4 = closed with no changes (some builds still send a url);
    # 6 = force-save while editing.
    if st in (2, 4, 6) and download_url:
        row = _callback_resolve_file_row(
            db,
            case_id=case_id,
            file_id=file_id,
            precedent_id=precedent_id,
            fee_scale_id=fee_scale_id,
            firm_letterhead_kind=firm_letterhead_kind,
        )
        if row is None:
            return {"error": 1}
        db.refresh(row)
        file_id = row.id

        # If the user discarded changes the session is released; skip saving — unless this save was
        # initiated by POST /oo-force-save (``oo_force_save_pending``). Without that flag, clearing
        # pending without bumping ``version`` leaves force-save waiters timing out with HTTP 504.
        active_sess = db.execute(
            select(FileEditSession).where(
                FileEditSession.file_id == file_id,
                FileEditSession.released_at.is_(None),
            )
        ).scalars().first()
        if active_sess is None and not row.oo_force_save_pending:
            log.warning(
                "onlyoffice_callback: NO active session for file %s — skipping save (was discarded?)",
                file_id,
            )
            return {"error": 0}
        if active_sess is None:
            log.warning(
                "onlyoffice_callback: NO active session row for file %s — force-save pending; saving from DS url anyway",
                file_id,
            )
        else:
            log.warning("onlyoffice_callback: active session found, proceeding to save file %s", file_id)

        ensure_files_root()
        abs_path = (FILES_ROOT / row.storage_path).resolve()
        if not str(abs_path).startswith(str(FILES_ROOT)):
            log.error("Invalid storage path for file %s", file_id)
            return {"error": 1}

        fetch_url = _rewrite_oo_download_url(str(download_url))
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(fetch_url)
                r.raise_for_status()
                data = r.content
        except Exception as e:
            log.exception("ONLYOFFICE save download failed (url=%s): %s", fetch_url, e)
            return {"error": 1}

        data = finalize_stored_docx_bytes(
            data,
            filename=row.original_filename,
            mime_type=row.mime_type,
        )

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)

        # Remove pre-edit backup now that the new version is saved.
        backup_path = Path(str(abs_path) + ".oo_backup")
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception as exc:
                log.warning("Could not delete backup %s: %s", backup_path, exc)

        row.version = (row.version or 1) + 1
        row.size_bytes = len(data)
        row.updated_at = datetime.now(timezone.utc)
        row.oo_force_save_pending = False
        if case_id is not None:
            from app.quote_portal_service import supersede_pending_quote_deliveries

            supersede_pending_quote_deliveries(db, row.id)
        db.add(row)
        db.commit()

        action, meta_extra = _oo_save_audit_action_meta(
            precedent_id=precedent_id,
            case_id=case_id,
            firm_letterhead_kind=firm_letterhead_kind,
        )
        log_event(
            db,
            actor_user_id=None,
            action=action,
            entity_type="file",
            entity_id=str(row.id),
            meta={**meta_extra, "version": row.version, "size_bytes": len(data)},
        )
        return {"error": 0}

    # Force-save with no edits: DS may omit ``url`` (status 4 is “closed, no changes”; some builds also omit url on 2/6).
    if st in (2, 4, 6) and not download_url:
        row = _callback_resolve_file_row(
            db,
            case_id=case_id,
            file_id=file_id,
            precedent_id=precedent_id,
            fee_scale_id=fee_scale_id,
            firm_letterhead_kind=firm_letterhead_kind,
        )
        if row is None:
            return {"error": 1}
        db.refresh(row)
        if not row.oo_force_save_pending:
            return {"error": 0}
        active_sess = db.execute(
            select(FileEditSession).where(
                FileEditSession.file_id == row.id,
                FileEditSession.released_at.is_(None),
            )
        ).scalars().first()
        if active_sess is None:
            log.warning(
                "onlyoffice_callback: force-save pending but no session row for file %s — metadata-only ack",
                row.id,
            )
        _oo_ack_unchanged_force_save(
            db,
            row,
            precedent_id=precedent_id,
            case_id=case_id,
            firm_letterhead_kind=firm_letterhead_kind,
            status_code=st,
        )
        return {"error": 0}

    # 1 = editing; 3 = save error; 4 = closed with no changes (handled above when pending); etc.
    return {"error": 0}
