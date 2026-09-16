"""Case file upload and Office/quote compose helpers."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.audit import log_event
from app.case_folder_service import (
    _FOLDER_BUSY_DETAIL,
    _FOLDER_GONE_DETAIL,
    _db_now,
    _folder_destination_exists,
    _prepare_upload_folder,
    _touch_folder_upload_settle,
    _try_lock_case_folder_ops_session,
    _unlock_case_folder_ops_session,
)
from app.compose_merge import merge_compose_docx_bytes
from app.compose_quote import merge_compose_quote_docx_bytes, quote_lines_snapshot_payload, resolve_compose_quote_lines
from app.deps import require_case_access
from app.file_eml_service import (
    convert_case_upload_msg_to_eml_if_applicable,
    _eml_parse_date_header,
    _eml_parse_from_header,
    _eml_parse_message_id_from_header,
    _infer_source_mail_is_outbound,
)
from app.file_storage import (
    case_file_paths,
    commit_keeping_stored_file,
    ensure_files_root,
    sanitize_folder_path,
    stream_upload_to_path,
    unlink_stored_file,
)
from app.finance_service import sync_finance_from_quote
from app.graph_outbound_service import link_outlook_graph_metadata_for_eml_file
from app.models import CaseQuoteSnapshot, File as DbFile, FileCategory, User
from app.owa_urls import outlook_graph_message_id_storable as _outlook_graph_message_id_storable
from app.portal_notifications import notify_portal_contacts_files_added_batch
from app.schemas import ComposeOfficeDocumentIn, ComposeQuoteIn
from app.upload_limits import max_upload_bytes

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upload_case_file(
    case_id: uuid.UUID,
    upload: UploadFile,
    *,
    folder: str = "",
    parent_file_id: uuid.UUID | None = None,
    notify_portal_contacts: bool = False,
    compose_precedent_id: uuid.UUID | None = None,
    compose_case_contact_id: uuid.UUID | None = None,
    compose_global_contact_id: uuid.UUID | None = None,
    source_imap_mbox: str | None = None,
    source_imap_uid: str | None = None,
    source_internet_message_id: str | None = None,
    outlook_item_id: str | None = None,
    outlook_conversation_id: str | None = None,
    user: User,
    db: Session,
) -> dict:
    require_case_access(case_id, user, db)
    ensure_files_root()

    try:
        folder = sanitize_folder_path(folder)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    parent: DbFile | None = None
    if parent_file_id is not None:
        parent = db.get(DbFile, parent_file_id)
        if not parent or parent.case_id != case_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parent_file_id is invalid")

    # Session-level lock for the whole upload (including stream) so concurrent recursive
    # folder delete cannot both succeed and then remove the new object (CL-09).
    session_folder_locked = False
    if folder:
        if not _try_lock_case_folder_ops_session(db, case_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FOLDER_BUSY_DETAIL)
        session_folder_locked = True
        if not _folder_destination_exists(db, case_id, folder):
            _unlock_case_folder_ops_session(db, case_id)
            session_folder_locked = False
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FOLDER_GONE_DETAIL)

    file_id = uuid.uuid4()
    original = upload.filename or "upload.bin"
    paths = case_file_paths(case_id=case_id, file_id=file_id, original_filename=original, folder_path=folder)

    disk_written = False
    try:
        try:
            size = stream_upload_to_path(paths.abs_path, upload.file, max_bytes=max_upload_bytes())
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e)) from e
        disk_written = True

        original, paths, size = convert_case_upload_msg_to_eml_if_applicable(
            case_id=case_id,
            file_id=file_id,
            folder_path=folder,
            original_filename=original,
            paths=paths,
        )

        mime = upload.content_type or (mimetypes.guess_type(original)[0] or "application/octet-stream")
        mime_base = mime.split(";", 1)[0].strip().lower()
        guessed = mimetypes.guess_type(original)[0]
        # Browsers often send application/octet-stream for Office files; prefer extension-based type.
        if mime_base == "application/octet-stream" and guessed:
            mime = guessed
        mime_base = mime.split(";", 1)[0].strip().lower()
        if original.lower().endswith(".eml"):
            mime = "message/rfc822"
            mime_base = "message/rfc822"

        outlook_rest_id = (outlook_item_id or "").strip() or None
        outlook_conv_id = (outlook_conversation_id or "").strip() or None
        if parent_file_id is not None:
            outlook_rest_id = None
            outlook_conv_id = None

        internet_mid: str | None = (source_internet_message_id or "").strip() or None
        if parent_file_id is None and not internet_mid:
            low = original.lower()
            if mime_base == "message/rfc822" or low.endswith(".eml"):
                internet_mid = _eml_parse_message_id_from_header(paths.abs_path)

        smbox = (source_imap_mbox or "").strip() or None
        suid = (source_imap_uid or "").strip() or None
        if parent_file_id is not None and (smbox is not None or suid is not None):
            # Only the parent email row should carry IMAP pointers.
            smbox = None
            suid = None

        from_name: str | None = None
        from_email_addr: str | None = None
        mail_outbound: bool | None = None
        mail_header_date: datetime | None = None
        if parent_file_id is None:
            low = original.lower()
            if mime_base == "message/rfc822" or low.endswith(".eml"):
                from_name, from_email_addr = _eml_parse_from_header(paths.abs_path)
                mail_outbound = _infer_source_mail_is_outbound(smbox, from_email_addr, user.email)
                mail_header_date = _eml_parse_date_header(paths.abs_path)

        now = _db_now(db)
        row = DbFile(
            id=file_id,
            case_id=case_id,
            owner_id=user.id,
            category=FileCategory.case_document,
            storage_path=paths.rel_path,
            folder_path=paths.folder_path,
            parent_file_id=parent_file_id,
            source_imap_mbox=smbox,
            source_imap_uid=suid,
            source_mail_from_name=from_name,
            source_mail_from_email=from_email_addr,
            source_mail_is_outbound=mail_outbound,
            source_internet_message_id=internet_mid,
            source_mail_date=mail_header_date,
            source_outlook_conversation_id=outlook_conv_id,
            source_outlook_item_id=outlook_rest_id,
            outlook_graph_message_id=_outlook_graph_message_id_storable(outlook_rest_id),
            outlook_web_link=None,
            is_pinned=False,
            original_filename=original,
            mime_type=mime,
            size_bytes=size,
            version=1,
            checksum=None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        if folder and not _folder_destination_exists(db, case_id, folder):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_FOLDER_GONE_DETAIL)
        if folder:
            _touch_folder_upload_settle(db, case_id, folder)
        log_event(
            db,
            actor_user_id=user.id,
            action="case.file.upload",
            entity_type="file",
            entity_id=str(row.id),
            meta={
                "case_id": str(case_id),
                "filename": row.original_filename,
                "size_bytes": row.size_bytes,
                "folder": paths.folder_path,
                "parent_file_id": str(parent_file_id) if parent_file_id else None,
                "compose_precedent_id": str(compose_precedent_id) if compose_precedent_id else None,
                "compose_case_contact_id": str(compose_case_contact_id) if compose_case_contact_id else None,
                "compose_global_contact_id": str(compose_global_contact_id) if compose_global_contact_id else None,
            },
        )
        db.commit()
        disk_written = False
    finally:
        if session_folder_locked:
            try:
                _unlock_case_folder_ops_session(db, case_id)
            except Exception:
                log.exception("failed to release folder-ops session lock case_id=%s", case_id)
            session_folder_locked = False
        if disk_written:
            unlink_stored_file(paths.abs_path)

    db.refresh(row)
    if notify_portal_contacts:
        notify_portal_contacts_files_added_batch(
            db,
            case_id=case_id,
            folder_path=paths.folder_path or "",
            filenames=[row.original_filename],
            actor_user_id=user.id,
        )

    if parent_file_id is None and (mime_base == "message/rfc822" or original.lower().endswith(".eml")):
        try:
            link_outlook_graph_metadata_for_eml_file(db, row, paths.abs_path)
        except Exception:
            log.warning(
                "upload_case_file: could not link Outlook Graph metadata for %s",
                original,
                exc_info=True,
            )

    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
    }


def compose_office_document(
    case_id: uuid.UUID,
    body: ComposeOfficeDocumentIn,
    user: User,
    db: Session,
) -> dict:
    """Create a new .docx from a precedent template or from the reserved blank letter / empty document path.

    Letter compose should send ``compose_office_role: \"letter\"`` when ``precedent_id`` is null so the server
    can substitute the ``BLANK_LETTER`` global template.
    """
    require_case_access(case_id, user, db)
    ensure_files_root()
    orig = body.original_filename.strip()
    if not orig.lower().endswith(".docx"):
        orig = f"{Path(orig).stem or 'Document'}.docx"

    src_bytes, mime = merge_compose_docx_bytes(db, case_id, body, require_precedent_kind=None)

    file_id = uuid.uuid4()
    folder = _prepare_upload_folder(db, case_id, body.folder or "")
    paths = case_file_paths(case_id=case_id, file_id=file_id, original_filename=orig, folder_path=folder)
    paths.abs_path.write_bytes(src_bytes)
    size = len(src_bytes)
    now = _utcnow()
    row = DbFile(
        id=file_id,
        case_id=case_id,
        owner_id=user.id,
        category=FileCategory.case_document,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        parent_file_id=None,
        source_imap_mbox=None,
        source_imap_uid=None,
        is_pinned=False,
        original_filename=orig,
        mime_type=mime,
        size_bytes=size,
        version=1,
        checksum=None,
        oo_compose_pending=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.compose_office",
        entity_type="file",
        entity_id=str(row.id),
        meta={"case_id": str(case_id), "precedent_id": str(body.precedent_id) if body.precedent_id else None},
    )
    commit_keeping_stored_file(db, paths.abs_path)
    db.refresh(row)
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
    }


def compose_quote_spreadsheet(
    case_id: uuid.UUID,
    body: ComposeQuoteIn,
    user: User,
    db: Session,
) -> dict:
    """Create a new quote .docx: quote letterhead template + fee table from the fee scale."""
    require_case_access(case_id, user, db)
    ensure_files_root()
    orig = body.original_filename.strip()
    if not orig.lower().endswith(".docx"):
        orig = f"{Path(orig).stem or 'Quote'}.docx"

    try:
        src_bytes, mime = merge_compose_quote_docx_bytes(db, case_id, body)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve

    file_id = uuid.uuid4()
    folder = sanitize_folder_path(body.folder or "")
    paths = case_file_paths(case_id=case_id, file_id=file_id, original_filename=orig, folder_path=folder)
    paths.abs_path.write_bytes(src_bytes)
    size = len(src_bytes)
    now = _utcnow()
    row = DbFile(
        id=file_id,
        case_id=case_id,
        owner_id=user.id,
        category=FileCategory.case_document,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        parent_file_id=None,
        source_imap_mbox=None,
        source_imap_uid=None,
        is_pinned=False,
        original_filename=orig,
        mime_type=mime,
        size_bytes=size,
        version=1,
        checksum=None,
        oo_compose_pending=True,
        is_portal_quote=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    try:
        computed = resolve_compose_quote_lines(db, case_id, body)
        if computed:
            db.add(
                CaseQuoteSnapshot(
                    id=uuid.uuid4(),
                    case_id=case_id,
                    file_id=file_id,
                    quote_lines=quote_lines_snapshot_payload(computed),
                    created_at=now,
                )
            )
            sync_finance_from_quote(case_id, db, overwrite_existing=True)
    except ValueError:
        pass
    log_event(
        db,
        actor_user_id=user.id,
        action="case.file.compose_quote",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "case_id": str(case_id),
            "fee_scale_id": str(body.fee_scale_id) if body.fee_scale_id else None,
        },
    )
    commit_keeping_stored_file(db, paths.abs_path)
    db.refresh(row)
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
    }
