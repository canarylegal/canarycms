"""Portal browse / file helpers (grants, zip, upload, downloads, client actions)."""

from __future__ import annotations

import mimetypes
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.audit import log_event
from app.canary_sign_service import (
    list_for_contact as list_canary_sign_for_contact,
    list_pending_for_contact as list_pending_canary_sign_for_contact,
    portal_signing_view as canary_portal_signing_view,
    read_snapshot_pdf_bytes,
)
from app.download_headers import content_disposition_headers
from app.docusign_signing_service import (
    list_pending_for_contact as list_pending_docusign_for_contact,
    portal_signing_view as docusign_portal_signing_view,
    sync_envelope_status,
)
from app.file_storage import (
    FILES_ROOT,
    case_file_paths,
    ensure_files_root,
    path_is_under_files_root,
    stream_upload_to_path,
    unlink_stored_file,
)
from app.models import (
    Case,
    CanarySignRecipient,
    CanarySignRecipientStatus,
    CanarySignRequest,
    CanarySignStatus,
    Contact,
    ContactPortalGrant,
    File,
    FileCategory,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.permission_checks import user_may_be_fee_earner
from app.portal_activity import log_portal_activity
from app.portal_case import filter_grants_for_portal_enabled_cases
from app.portal_form_service import (
    list_pending_for_contact as list_pending_forms_for_contact,
    portal_form_detail,
)
from app.portal_notifications import notify_portal_staff_client_upload
from app.portal_service import (
    browse_grant_folder,
    client_matter_description,
    contact_display_name,
    default_grant_label,
    ensure_upload_folder_allowed,
    get_portal_grant_file,
    get_grant_for_contact,
    grant_folder_display_name,
    list_active_grants_for_contact,
    list_active_grants_for_matter_session,
    list_grant_files,
    relative_folder_under_grant,
)
from app.quote_portal_service import (
    get_quote_delivery_file_for_contact,
    list_pending_approvals_for_grant,
    list_pending_quote_deliveries_for_contact,
    portal_quote_delivery_view,
)
from app.schemas import (
    PortalBrowseOut,
    PortalCanarySignOut,
    PortalClientActionItemOut,
    PortalClientActionsOut,
    PortalDocusignSigningOut,
    PortalFileOut,
    PortalFormPendingOut,
    PortalGrantSummaryOut,
    PortalQuoteDeliveryViewOut,
    PortalSessionOut,
)
from app.security import (
    PortalSessionPayload,
    create_portal_file_open_token,
    decode_portal_file_open_token,
)
from app.upload_limits import content_disposition_for_mime, max_upload_bytes


def unlink_if_exists(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def safe_zip_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in (name or "").strip())
    return cleaned[:120] or "folder"


def grant_summaries(
    db: Session,
    contact_id: uuid.UUID,
    *,
    case_id: uuid.UUID | None = None,
) -> list[PortalGrantSummaryOut]:
    from app.portal_grant_views import count_new_files_for_grant, get_grant_last_viewed_at

    if case_id is not None:
        grants = filter_grants_for_portal_enabled_cases(
            db, list_active_grants_for_matter_session(db, contact_id=contact_id, case_id=case_id)
        )
    else:
        grants = filter_grants_for_portal_enabled_cases(db, list_active_grants_for_contact(db, contact_id))
    out: list[PortalGrantSummaryOut] = []
    for g in grants:
        case = db.get(Case, g.case_id)
        case_title = (case.title or "").strip() if case else "Matter"
        if not case_title:
            case_title = "Matter"
        folder_label = grant_folder_display_name(g)
        last_viewed = get_grant_last_viewed_at(db, contact_id=contact_id, grant_id=g.id)
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
                new_file_count=count_new_files_for_grant(db, g, contact_id=contact_id),
                last_viewed_at=last_viewed,
            )
        )
    return out


def quote_delivery_view(db: Session, delivery: QuotePortalDelivery) -> PortalQuoteDeliveryViewOut:
    grant = db.get(ContactPortalGrant, delivery.grant_id) if delivery.grant_id else None
    return PortalQuoteDeliveryViewOut(**portal_quote_delivery_view(db, delivery, grant=grant))


def form_pending_out(db: Session, submission: PortalFormSubmission) -> PortalFormPendingOut:
    detail = portal_form_detail(db, submission)
    case = db.get(Case, submission.case_id)
    label = client_matter_description(case)
    return PortalFormPendingOut(
        id=submission.id,
        template_name=detail.get("template_name") or "",
        template_reference=detail.get("template_reference") or "",
        status=submission.status.value,
        sent_at=submission.sent_at,
        case_id=submission.case_id,
        matter_label=label,
    )


def file_out(
    grant: ContactPortalGrant,
    row: File,
    *,
    is_new: bool = False,
) -> PortalFileOut:
    from app.file_storage import decode_folder_path_for_display

    rel = relative_folder_under_grant(grant_folder=grant.folder_path or "", absolute_folder=row.folder_path or "")
    display = rel.split("/")[-1] if rel else (row.folder_path or "Documents")
    if rel and "/" in rel:
        display = rel
    elif rel:
        display = rel
    else:
        display = ""
    if display:
        display = decode_folder_path_for_display(display)
    return PortalFileOut(
        id=row.id,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        folder_path=row.folder_path or "",
        folder_display=display,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_new=is_new,
    )


def pending_forms_for_grant(db: Session, *, contact: Contact, grant: ContactPortalGrant) -> list[PortalFormPendingOut]:
    out: list[PortalFormPendingOut] = []
    for sub in list_pending_forms_for_contact(db, contact.id):
        if sub.case_id != grant.case_id:
            continue
        detail = portal_form_detail(db, sub)
        case = db.get(Case, sub.case_id)
        label = client_matter_description(case)
        out.append(
            PortalFormPendingOut(
                id=sub.id,
                template_name=detail.get("template_name") or "",
                template_reference=detail.get("template_reference") or "",
                status=sub.status.value,
                sent_at=sub.sent_at,
                case_id=sub.case_id,
                matter_label=label,
            )
        )
    return out


def canary_request_for_contact(
    db: Session, request_id: uuid.UUID, contact_id: uuid.UUID
) -> tuple[CanarySignRequest, CanarySignRecipient]:
    req = db.get(CanarySignRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    recip = db.execute(
        select(CanarySignRecipient)
        .where(
            CanarySignRecipient.signing_request_id == req.id,
            CanarySignRecipient.contact_id == contact_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if recip is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a recipient on this signing request")
    return req, recip


def portal_session(
    contact: Contact,
    session: PortalSessionPayload,
    db: Session,
) -> PortalSessionOut:
    focus_case_id = None
    case_filter = None
    if getattr(session, "audience", "client") == "exchange" and session.case_id:
        try:
            focus_case_id = uuid.UUID(session.case_id)
            case_filter = focus_case_id
        except ValueError:
            focus_case_id = None
    return PortalSessionOut(
        contact_name=contact_display_name(contact),
        grants=grant_summaries(db, contact.id, case_id=case_filter),
        staff_preview=session.staff_preview,
        audience="exchange" if getattr(session, "audience", "client") == "exchange" else "client",
        focus_case_id=focus_case_id,
    )


def browse_grant(
    grant_id: uuid.UUID,
    *,
    subfolder: str,
    contact: Contact,
    session: PortalSessionPayload,
    db: Session,
) -> PortalBrowseOut:
    from app.portal_grant_views import file_is_new_since, get_grant_last_viewed_at

    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if getattr(session, "audience", "client") == "exchange" and session.case_id:
        if str(grant.case_id) != session.case_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Area not found")
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    rel, child_names, files_here = browse_grant_folder(db, grant, subfolder=subfolder)
    exchange = getattr(session, "audience", "client") == "exchange"
    pending = [] if exchange else list_pending_approvals_for_grant(db, contact_id=contact.id, grant=grant)
    pending_ids = {d.file_id for d in pending}
    last_viewed = get_grant_last_viewed_at(db, contact_id=contact.id, grant_id=grant.id)
    visible = [f for f in files_here if f.id not in pending_ids]
    file_outs = [file_out(grant, f, is_new=file_is_new_since(f, last_viewed)) for f in visible]
    crumbs: list[str] = []
    if rel:
        crumbs = rel.split("/")
    return PortalBrowseOut(
        subfolder=rel,
        breadcrumb=crumbs,
        subfolders=child_names,
        files=file_outs,
        pending_approvals=[PortalQuoteDeliveryViewOut(**portal_quote_delivery_view(db, d, grant=grant)) for d in pending],
        pending_docusign_signings=(
            []
            if exchange
            else [
                PortalDocusignSigningOut(**docusign_portal_signing_view(db, req, contact_id=contact.id))
                for req, _recip in list_pending_docusign_for_contact(db, contact.id)
            ]
        ),
        pending_canary_signings=(
            []
            if exchange
            else [
                PortalCanarySignOut(**canary_portal_signing_view(db, req, contact_id=contact.id))
                for req, _recip in list_pending_canary_sign_for_contact(db, contact.id)
            ]
        ),
        pending_portal_forms=[] if exchange else pending_forms_for_grant(db, contact=contact, grant=grant),
        new_file_count=sum(1 for f in file_outs if f.is_new),
        last_viewed_at=last_viewed,
    )


def list_forms(contact: Contact, db: Session) -> list[PortalFormPendingOut]:
    out: list[PortalFormPendingOut] = []
    for sub in list_pending_forms_for_contact(db, contact.id):
        detail = portal_form_detail(db, sub)
        case = db.get(Case, sub.case_id)
        label = client_matter_description(case)
        out.append(
            PortalFormPendingOut(
                id=sub.id,
                template_name=detail.get("template_name") or "",
                template_reference=detail.get("template_reference") or "",
                status=sub.status.value,
                sent_at=sub.sent_at,
                case_id=sub.case_id,
                matter_label=label,
            )
        )
    return out


def list_files(grant_id: uuid.UUID, contact: Contact, db: Session) -> list[PortalFileOut]:
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    rows = list_grant_files(db, grant)
    return [file_out(grant, f) for f in rows]


def download_grant_zip(grant_id: uuid.UUID, contact: Contact, db: Session):
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    rows = list_grant_files(db, grant)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No files to download")
    ensure_files_root()
    zip_label = safe_zip_name(grant_folder_display_name(grant))
    arc_taken: set[str] = set()
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for row in rows:
                abs_path = (FILES_ROOT / row.storage_path).resolve()
                if not path_is_under_files_root(abs_path) or not abs_path.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File missing on disk: {row.original_filename}",
                    )
                arc = safe_zip_name(row.original_filename)
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
        db.commit()
        return FileResponse(
            path=tmp,
            media_type="application/zip",
            filename=f"{zip_label}.zip",
            content_disposition_type="attachment",
            background=BackgroundTask(unlink_if_exists, tmp),
        )
    except HTTPException:
        if tmp:
            unlink_if_exists(tmp)
        raise
    except Exception:
        if tmp:
            unlink_if_exists(tmp)
        raise


def download_file(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    *,
    download: bool,
    contact: Contact,
    db: Session,
):
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    row = get_portal_grant_file(db, grant, contact.id, file_id)
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    log_event(
        db,
        actor_user_id=None,
        action="portal.file.download" if download else "portal.file.open",
        entity_type="file",
        entity_id=str(row.id),
        meta={"contact_id": str(contact.id), "grant_id": str(grant.id), "case_id": str(grant.case_id)},
    )
    log_portal_activity(
        db,
        case_id=grant.case_id,
        contact_id=contact.id,
        grant_id=grant.id,
        action="portal.file.download" if download else "portal.file.open",
        summary=f"{contact_display_name(contact)} {'downloaded' if download else 'opened'} {row.original_filename}",
    )
    db.commit()
    return FileResponse(
        path=str(abs_path),
        media_type=row.mime_type,
        filename=row.original_filename,
        content_disposition_type=content_disposition_for_mime(row.mime_type, download=download),
    )


def issue_file_open_token(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    contact: Contact,
    db: Session,
) -> dict[str, str]:
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    get_portal_grant_file(db, grant, contact.id, file_id)
    tok = create_portal_file_open_token(
        contact_id=str(contact.id),
        grant_id=str(grant.id),
        file_id=str(file_id),
    )
    return {"token": tok}


def open_file_with_token(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    token: str,
    db: Session,
):
    try:
        payload = decode_portal_file_open_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired link")
    try:
        contact_id = uuid.UUID(payload.contact_id)
        if uuid.UUID(payload.grant_id) != grant_id or uuid.UUID(payload.file_id) != file_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid link")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid link") from e

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid link")

    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    row = get_portal_grant_file(db, grant, contact.id, file_id)
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")

    log_event(
        db,
        actor_user_id=None,
        action="portal.file.open",
        entity_type="file",
        entity_id=str(row.id),
        meta={"contact_id": str(contact.id), "grant_id": str(grant.id), "case_id": str(grant.case_id)},
    )
    log_portal_activity(
        db,
        case_id=grant.case_id,
        contact_id=contact.id,
        grant_id=grant.id,
        action="portal.file.open",
        summary=f"{contact_display_name(contact)} opened {row.original_filename}",
    )
    db.commit()
    return FileResponse(
        path=str(abs_path),
        media_type=row.mime_type or "application/octet-stream",
        filename=row.original_filename,
        content_disposition_type=content_disposition_for_mime(row.mime_type, download=False),
    )


def upload_file(
    grant_id: uuid.UUID,
    upload: UploadFile,
    *,
    folder: str,
    contact: Contact,
    session: PortalSessionPayload,
    db: Session,
) -> PortalFileOut:
    from app.deps import require_portal_not_preview

    require_portal_not_preview(session)
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if getattr(session, "audience", "client") == "exchange" and session.case_id:
        if str(grant.case_id) != session.case_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Area not found")
    target_folder = ensure_upload_folder_allowed(grant=grant, folder=folder or grant.folder_path or "")
    case = db.get(Case, grant.case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    owner = db.get(User, case.fee_earner_user_id)
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Matter fee earner missing")
    if not user_may_be_fee_earner(owner, db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This matter's fee earner is not configured correctly. Ask your firm to assign a fee earner.",
        )

    ensure_files_root()
    file_id = uuid.uuid4()
    original = upload.filename or "upload.bin"
    paths = case_file_paths(
        case_id=grant.case_id,
        file_id=file_id,
        original_filename=original,
        folder_path=target_folder,
    )
    try:
        size = stream_upload_to_path(paths.abs_path, upload.file, max_bytes=max_upload_bytes())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e)) from e

    disk_written = True
    try:
        mime = upload.content_type or (mimetypes.guess_type(original)[0] or "application/octet-stream")
        now = datetime.now(timezone.utc)
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
            created_at=now,
            updated_at=now,
        )
        db.add(row)
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
        log_portal_activity(
            db,
            case_id=grant.case_id,
            contact_id=contact.id,
            grant_id=grant.id,
            action="portal.file.upload",
            summary=f"{contact_display_name(contact)} uploaded {row.original_filename}",
        )
        notify_portal_staff_client_upload(
            db,
            case_id=grant.case_id,
            contact=contact,
            grant=grant,
            filename=row.original_filename,
        )
        db.commit()
        disk_written = False
    finally:
        if disk_written:
            unlink_stored_file(paths.abs_path)

    db.refresh(row)
    return file_out(grant, row)


def download_quote_delivery_file(
    delivery_id: uuid.UUID,
    *,
    download: bool,
    contact: Contact,
    db: Session,
):
    delivery, row = get_quote_delivery_file_for_contact(
        db,
        delivery_id=delivery_id,
        contact_id=contact.id,
    )
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    log_event(
        db,
        actor_user_id=None,
        action="portal.quote.file.download" if download else "portal.quote.file.open",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "contact_id": str(contact.id),
            "case_id": str(delivery.case_id),
            "delivery_id": str(delivery.id),
        },
    )
    log_portal_activity(
        db,
        case_id=delivery.case_id,
        contact_id=contact.id,
        grant_id=delivery.grant_id,
        action="portal.quote.file.download" if download else "portal.quote.file.open",
        summary=f"{contact_display_name(contact)} {'downloaded' if download else 'opened'} {row.original_filename}",
    )
    db.commit()
    return FileResponse(
        path=str(abs_path),
        media_type=row.mime_type,
        filename=row.original_filename,
        content_disposition_type=content_disposition_for_mime(row.mime_type, download=download),
    )


def canary_sign_pdf(request_id: uuid.UUID, contact: Contact, db: Session):
    req, _recip = canary_request_for_contact(db, request_id, contact.id)
    raw = read_snapshot_pdf_bytes(db, req)
    filename = f"{(req.subject or 'document')[:80]}.pdf"
    return Response(
        content=raw,
        media_type="application/pdf",
        headers=content_disposition_headers(filename, disposition="inline"),
    )


def client_actions(contact: Contact, db: Session) -> PortalClientActionsOut:
    outstanding: list[PortalClientActionItemOut] = []
    complete: list[PortalClientActionItemOut] = []
    inactive: list[PortalClientActionItemOut] = []

    for d in list_pending_quote_deliveries_for_contact(db, contact_id=contact.id):
        view = portal_quote_delivery_view(db, d)
        outstanding.append(
            PortalClientActionItemOut(
                kind="quote",
                id=d.id,
                title=view.get("original_filename") or "Quote",
                status=d.status.value,
                matter_label=view.get("case_title") or "",
                badge="Quote",
                href_key=f"quote:{d.id}",
                case_id=d.case_id,
            )
        )

    quote_rows = db.execute(
        select(QuotePortalDelivery).where(QuotePortalDelivery.contact_id == contact.id)
    ).scalars().all()
    for d in quote_rows:
        if d.status == QuotePortalDeliveryStatus.pending:
            continue
        view = portal_quote_delivery_view(db, d)
        item = PortalClientActionItemOut(
            kind="quote",
            id=d.id,
            title=view.get("original_filename") or "Quote",
            status=d.status.value,
            matter_label=view.get("case_title") or "",
            badge="Quote",
            href_key=f"quote:{d.id}",
            case_id=d.case_id,
        )
        if d.status == QuotePortalDeliveryStatus.accepted:
            complete.append(item)
        else:
            inactive.append(item)

    for sub in list_pending_forms_for_contact(db, contact.id):
        case = db.get(Case, sub.case_id)
        outstanding.append(
            PortalClientActionItemOut(
                kind="form",
                id=sub.id,
                title=form_pending_out(db, sub).template_name or "Form",
                status=sub.status.value,
                matter_label=client_matter_description(case),
                badge="Form",
                href_key=f"form:{sub.id}",
                case_id=sub.case_id,
            )
        )
    form_all = db.execute(
        select(PortalFormSubmission).where(PortalFormSubmission.contact_id == contact.id)
    ).scalars().all()
    for sub in form_all:
        if sub.status == PortalFormSubmissionStatus.pending:
            continue
        case = db.get(Case, sub.case_id)
        item = PortalClientActionItemOut(
            kind="form",
            id=sub.id,
            title=form_pending_out(db, sub).template_name or "Form",
            status=sub.status.value,
            matter_label=client_matter_description(case),
            badge="Form",
            href_key=f"form:{sub.id}",
            case_id=sub.case_id,
        )
        if sub.status == PortalFormSubmissionStatus.completed:
            complete.append(item)
        else:
            inactive.append(item)

    for req, recip in list_canary_sign_for_contact(db, contact.id):
        case = db.get(Case, req.case_id)
        item = PortalClientActionItemOut(
            kind="canary_sign",
            id=req.id,
            title=req.subject,
            status=req.status.value,
            matter_label=client_matter_description(case),
            badge="Sign",
            href_key=f"canary_sign:{req.id}",
            case_id=req.case_id,
        )
        if req.status == CanarySignStatus.pending and recip.status in (
            CanarySignRecipientStatus.pending,
            CanarySignRecipientStatus.viewed,
        ):
            outstanding.append(item)
        elif req.status == CanarySignStatus.completed or recip.status == CanarySignRecipientStatus.signed:
            complete.append(item)
        else:
            inactive.append(item)

    for req, recip in list_pending_docusign_for_contact(db, contact.id):
        sync_envelope_status(db, req)
        if req.status.value != "pending":
            continue
        view = docusign_portal_signing_view(db, req, contact_id=contact.id)
        outstanding.append(
            PortalClientActionItemOut(
                kind="docusign",
                id=req.id,
                title=view.get("envelope_subject") or "Document to sign",
                status=req.status.value,
                matter_label="",
                badge="DocuSign",
                href_key=f"docusign:{req.id}",
                case_id=req.case_id,
            )
        )

    return PortalClientActionsOut(outstanding=outstanding, complete=complete, inactive=inactive)
