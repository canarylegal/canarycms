"""ONLYOFFICE in-browser edit + desktop WebDAV checkout helpers for case files."""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import jwt as pyjwt
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.canary_public_url import canary_public_url, onlyoffice_browser_public_base
from app.case_file_mutate_service import _erase_case_file_tree
from app.deps import require_case_access
from app.desktop_edit_session import acquire_file_edit_session
from app.feature_flags import onlyoffice_editor_customization, open_pdf_in_onlyoffice
from app.file_storage import FILES_ROOT, ensure_files_root
from app.models import File as DbFile, FileEditSession, User
from app.onlyoffice_file_types import (
    _ONLYOFFICE_DOC_PERMISSIONS,
    _correct_file_type,
    _onlyoffice_types_for_file,
)
from app.onlyoffice_force_save import (
    OoForceSavePhase,
    oo_force_save_arm,
    oo_force_save_command_service,
    oo_force_save_issue_command,
    oo_force_save_wait,
)
from app.onlyoffice_ssrf_url import default_internal_base_for_ds, normalize_onlyoffice_ssrf_base
from app.portal_notifications import notify_portal_contacts_files_added_batch
from app.routers.onlyoffice import (
    create_case_file_from_onlyoffice_pdf_export,
    persist_onlyoffice_browser_url_to_file,
)
from app.schemas import (
    FileDesktopCheckoutOut,
    FileEditSessionStatusOut,
    OnlyofficeEditorConfigOut,
    OoExportPdfIn,
    OoExportPdfOut,
    OoPersistDownloadIn,
    PublishComposeIn,
)

log = logging.getLogger(__name__)


def _redact_webdav_url_for_log(url: str) -> str:
    """Avoid leaking session tokens in logs."""
    return re.sub(r"(/webdav/sessions/)[^/]+(/[^/]+)$", r"\1<token>\2", url)


def _canary_public_url() -> str:
    return canary_public_url()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _onlyoffice_cli_hint() -> str:
    """ONLYOFFICE DesktopEditors treats CLI arguments as *local file paths* only, not http(s) URLs.

    Running ``desktopeditors 'https://…/webdav/…'`` makes the app look for a file literally named like
    the URL string, which surfaces as "file type is not supported". Prefer **Edit in browser**
    (Document Server) or an OS WebDAV mount. We return an empty string so clients do not suggest a
    broken terminal command.
    """
    return ""


def checkout_desktop_edit(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User,
    db: Session,
) -> FileDesktopCheckoutOut:
    require_case_access(case_id, user, db)
    sess, row = acquire_file_edit_session(db, case_id=case_id, file_id=file_id, user=user)

    base = _canary_public_url()
    fn = Path(row.original_filename).name
    enc = quote(fn, safe="")
    file_url = f"{base}/webdav/sessions/{sess.token}/{enc}"
    folder_url = f"{base}/webdav/sessions/{sess.token}/"
    log.info(
        "checkout_edit file_id=%s case_id=%s webdav_origin=%s (if ONLYOFFICE never hits the server, logs will show "
        "this line but no following /webdav access lines)",
        row.id,
        case_id,
        base,
    )
    onlyoffice_cli_hint = _onlyoffice_cli_hint()
    instructions = (
        "Prefer Canary \"Edit in browser (ONLYOFFICE)\". For desktop editing, mount the folder URL with "
        "davfs2/GVfs (or another WebDAV client) and open the file locally, or paste the file URL into a "
        "desktop app that supports remote WebDAV URLs. ONLYOFFICE Desktop CLI does not accept http(s) URLs. "
        "Use Stop desktop editing when finished."
    )

    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.checkout_edit",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), "expires_at": sess.expires_at.isoformat()},
    )

    return FileDesktopCheckoutOut(
        token=sess.token,
        webdav_folder_url=folder_url,
        webdav_file_url=file_url,
        filename=fn,
        expires_at=sess.expires_at,
        instructions=instructions,
        onlyoffice_cli_hint=onlyoffice_cli_hint,
    )


def get_onlyoffice_editor_config(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    request: Request,
    response: Response,
    user: User,
    db: Session,
) -> OnlyofficeEditorConfigOut:
    require_case_access(case_id, user, db)
    secret = (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()
    ds_public = (os.getenv("ONLYOFFICE_DS_PUBLIC_URL") or "").strip().rstrip("/")
    # DS→Canary: prefer explicit ONLYOFFICE_APP_URL_INTERNAL, else resolved IPv4 for `backend` (see onlyoffice_ssrf_url).
    internal = default_internal_base_for_ds()
    if not secret or not ds_public:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "In-browser editing is not configured. Set ONLYOFFICE_JWT_SECRET, "
                "and ONLYOFFICE_DS_PUBLIC_URL (see docker-compose)."
            ),
        )

    sess, row = acquire_file_edit_session(db, case_id=case_id, file_id=file_id, user=user)

    # Create a backup of the pre-edit content so the user can discard changes.
    ensure_files_root()
    src = (FILES_ROOT / row.storage_path).resolve()
    try:
        backup = Path(str(src) + ".oo_backup")
        if src.exists() and not backup.exists():
            shutil.copy2(src, backup)
    except Exception as exc:
        log.warning("Could not create OnlyOffice backup for file %s: %s", row.id, exc)

    types = _onlyoffice_types_for_file(row.original_filename)
    if not types:
        ext = Path(row.original_filename or "").suffix.lower().lstrip(".")
        mt = (row.mime_type or "").lower()
        if not open_pdf_in_onlyoffice() and (
            ext == "pdf" or mt == "application/pdf" or mt.endswith("/pdf")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF files open in your browser from the case documents list, not in the in-browser editor.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This file type is not supported by the in-browser editor.",
        )
    doc_type, file_type = types
    # Correct fileType when the extension claims old binary format but the file is actually OOXML/ZIP.
    # e.g. a .DOC file that is really a DOCX (Word 2007+) — OO DS reports "download failed" otherwise.
    file_type = _correct_file_type(file_type, src)

    def _base(env_name: str) -> str:
        return (os.getenv(env_name) or "").strip().rstrip("/")

    # Document Server downloads document.url from *inside* the onlyoffice container. Must use a Docker-reachable
    # base (usually http://backend:8000). CANARY_PUBLIC_URL / host LAN IPs belong in WebDAV links for browsers only.
    doc_explicit = _base("ONLYOFFICE_DOCUMENT_URL")
    doc_base = (normalize_onlyoffice_ssrf_base(doc_explicit) if doc_explicit else "") or internal
    cb_url = f"{internal}/onlyoffice/callback?case_id={case_id}&file_id={file_id}"

    fn = Path(row.original_filename).name
    enc = quote(fn, safe="")
    # DS downloads document.url server-side (inside Docker); must use the Docker-reachable base.
    doc_url_for_ds = f"{doc_base}/webdav/sessions/{sess.token}/{enc}"
    # Plain (non-JWT) document.url.
    #
    # IMPORTANT: do NOT run SSRF normalization for the browser URL.
    # Normalization rewrites many private-ish IP ranges to `http://backend:8000` so the
    # Document Server container can fetch. That rewrite breaks the browser-side iframe because
    # the browser cannot reach Docker-internal hosts.
    #
    # Prefer the browser's actual origin when proxied (Vite/nginx X-Forwarded-Host) so client-side
    # ONLYOFFICE fetches (e.g. print preview) do not target localhost:8000 while the tab is on :5173.
    _plain_base = onlyoffice_browser_public_base(request)
    doc_url_for_browser = f"{_plain_base}/webdav/sessions/{sess.token}/{enc}"

    if doc_base != internal:
        log.info(
            "onlyoffice_config file_id=%s document_base=%s callback_base=%s (DS must fetch document_url; "
            "watch backend logs for GET /webdav/sessions/...)",
            row.id,
            doc_base,
            internal,
        )
    else:
        log.info(
            "onlyoffice_config file_id=%s document_base=callback_base=%s — expect GET /webdav/sessions/... from DS",
            row.id,
            internal,
        )
    doc_key = f"{file_id}_{row.version or 1}_{secrets.token_hex(6)}"

    # JWT must mirror the browser config (document + editorConfig + documentType). Omitting
    # documentType breaks PDF opens when JWT is enabled — DocsAPI reports invalid documentType.
    # Do not add type/width/height to the JWT (those break validation on some DS builds).
    #
    # ``lang``: Use ``en-GB`` so the editor uses British English (interface + document language defaults on DS 7.2+).
    # Two-letter ``en`` maps to US-centric behaviour and shows “English (United States)” for the document.
    # ``region``: ``en-GB`` for UK date/currency (spreadsheets) and measurement defaults where applicable.
    # The .docx should also set ``w:docDefaults`` to en-GB — see ``docx_util.ensure_docx_proofing_language_en_gb_bytes``.
    #
    # JWT document.url = Docker-internal URL (DS validates JWT and uses this to fetch the file).
    # Plain document.url = public URL (browser JS uses this; cannot reach Docker-internal hosts).
    # DS extracts document.url from the JWT, so the mismatch is intentional and harmless.
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
            "user": {
                "id": str(user.id),
                "name": user.display_name or user.email,
                "group": "Canary",
            },
            "customization": onlyoffice_editor_customization(file_type=file_type),
        },
    }
    # PyJWT matches what ONLYOFFICE Document Server (Node jsonwebtoken) expects better than python-jose.
    token = pyjwt.encode(jwt_payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    # Plain document dict for the browser: swap in the public URL so the browser can reach it.
    browser_document = dict(jwt_payload["document"])
    browser_document["url"] = doc_url_for_browser

    log.warning(
        "onlyoffice_jwt_built file_id=%s ds_doc_url=%s browser_doc_url=%s callback=%s",
        row.id,
        _redact_webdav_url_for_log(doc_url_for_ds),
        _redact_webdav_url_for_log(doc_url_for_browser),
        cb_url,
    )
    # Visible in browser DevTools → Network → onlyoffice-config → Response headers (token redacted).
    response.headers["X-Canary-Onlyoffice-Webdav-Url"] = _redact_webdav_url_for_log(doc_url_for_browser)
    response.headers["X-Canary-Onlyoffice-Document-Type"] = doc_type

    response.headers["Cache-Control"] = "no-store"

    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.onlyoffice_open",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id)},
    )

    return OnlyofficeEditorConfigOut(
        document_server_url=ds_public,
        token=token,
        document_type=doc_type,
        document=browser_document,
        editor_config=jwt_payload["editorConfig"],
        oo_compose_pending=bool(row.oo_compose_pending),
        folder_path=row.folder_path or "",
        original_filename=row.original_filename,
    )


async def oo_force_save(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    doc_key: str,
    phase: OoForceSavePhase,
    base_version: int | None,
    user: User,
    db: Session,
):
    """Persist in-browser ONLYOFFICE edits to Canary storage.

    Preferred flow (matches toolbar Save): arm → host ``serviceCommand('save')`` → wait.
    """
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

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
        await oo_force_save_issue_command(db, row, doc_key=doc_key, file_id=file_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if phase == "command_wait":
        await oo_force_save_command_service(db, row, doc_key=doc_key, file_id=file_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown phase: {phase}")


async def oo_export_pdf(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    body: OoExportPdfIn,
    user: User,
    db: Session,
) -> OoExportPdfOut:
    """Save ONLYOFFICE ``downloadAs('pdf')`` as a new case file (does not replace the source document)."""
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    created = await create_case_file_from_onlyoffice_pdf_export(
        db,
        row,
        browser_url=body.browser_url,
        case_id=case_id,
        user=user,
        filename=body.filename,
    )
    return OoExportPdfOut(file_id=created.id, original_filename=created.original_filename)


async def oo_persist_download(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    body: OoPersistDownloadIn,
    user: User,
    db: Session,
) -> None:
    """Persist ONLYOFFICE ``downloadAs`` export bytes to case file storage (PDF and Office)."""
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    await persist_onlyoffice_browser_url_to_file(
        db,
        row,
        browser_url=body.browser_url,
        case_id=case_id,
        precedent_id=None,
    )


def oo_save_status(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    base_version: int,
    user: User,
    db: Session,
) -> dict[str, int | bool]:
    """Poll whether ONLYOFFICE callback has persisted edits (version bumped past ``base_version``)."""
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    version = row.version or 1
    return {"saved": version > base_version, "version": version}


def publish_compose_office_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: PublishComposeIn | None,
    user: User,
    db: Session,
) -> None:
    """Show a compose-office document in the case file list (after OnlyOffice Save Changes).

    Idempotent: if the file is not a pending compose, succeeds with no change.
    """
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not row.oo_compose_pending:
        return
    row.oo_compose_pending = False
    row.updated_at = _utcnow()
    db.add(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.compose_publish",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id)},
    )
    db.commit()
    if payload and payload.notify_portal_contacts:
        notify_portal_contacts_files_added_batch(
            db,
            case_id=case_id,
            folder_path=row.folder_path or "",
            filenames=[row.original_filename],
            actor_user_id=user.id,
        )


def discard_onlyoffice_edit(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User,
    db: Session,
) -> None:
    """Discard in-browser edits: restore pre-edit backup and release the edit session."""
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    now = _utcnow()
    sess = db.execute(
        select(FileEditSession).where(
            FileEditSession.file_id == file_id,
            FileEditSession.user_id == user.id,
            FileEditSession.released_at.is_(None),
        )
    ).scalars().first()
    if sess is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active edit session")

    if row.oo_compose_pending:
        fid = row.id
        discard_name = row.original_filename
        _erase_case_file_tree(db, case_id, file_id)
        log_event(
            db,
            actor_user_id=user.id,
            action="case.file.compose_discard",
            entity_type="file",
            entity_id=str(fid),
            meta={"case_id": str(case_id), "filename": discard_name},
        )
        return

    if row.oo_force_save_pending:
        row.oo_force_save_pending = False
        db.add(row)

    # Restore backup if available.
    ensure_files_root()
    try:
        abs_path = (FILES_ROOT / row.storage_path).resolve()
        backup = Path(str(abs_path) + ".oo_backup")
        if backup.exists():
            shutil.copy2(backup, abs_path)
            backup.unlink()
            log.info("discard_edit: restored backup for file %s", file_id)
    except Exception as exc:
        log.warning("discard_edit: could not restore backup for file %s: %s", file_id, exc)

    sess.released_at = now
    db.add(sess)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.onlyoffice_discard",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id)},
    )
    db.commit()


def get_desktop_edit_session(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User,
    db: Session,
) -> FileEditSessionStatusOut:
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    now = _utcnow()
    sess = (
        db.execute(
            select(FileEditSession)
            .where(
                FileEditSession.file_id == file_id,
                FileEditSession.user_id == user.id,
                FileEditSession.released_at.is_(None),
                FileEditSession.expires_at > now,
            )
            .order_by(FileEditSession.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    if not sess:
        return FileEditSessionStatusOut(active=False)

    base = _canary_public_url()
    fn = Path(row.original_filename).name
    enc = quote(fn, safe="")
    return FileEditSessionStatusOut(
        active=True,
        expires_at=sess.expires_at,
        webdav_file_url=f"{base}/webdav/sessions/{sess.token}/{enc}",
    )


def release_desktop_edit(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User,
    db: Session,
) -> None:
    require_case_access(case_id, user, db)
    row = db.get(DbFile, file_id)
    if not row or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    now = _utcnow()
    sessions = (
        db.execute(
            select(FileEditSession).where(
                FileEditSession.file_id == file_id,
                FileEditSession.user_id == user.id,
                FileEditSession.released_at.is_(None),
                FileEditSession.expires_at > now,
            )
        )
        .scalars()
        .all()
    )
    if not sessions:
        db.commit()
        return None
    for s in sessions:
        s.released_at = now
        db.add(s)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.release_edit",
        entity_type="file",
        entity_id=str(file_id),
        meta={"case_id": str(case_id)},
    )
    db.commit()
    return None
