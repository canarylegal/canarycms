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
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.audit import log_event
from app.db import get_db
from app.deps import get_portal_contact
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.models import (
    Case,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    File,
    FileCategory,
    FirmSettings,
    QuotePortalDelivery,
    User,
)
from app.permission_checks import user_may_be_fee_earner
from app.portal_activity import log_portal_activity
from app.portal_notifications import notify_portal_staff_client_upload
from app.portal_case import filter_grants_for_portal_enabled_cases
from app.portal_service import (
    browse_grant_folder,
    contact_display_name,
    default_grant_label,
    ensure_upload_folder_allowed,
    find_portal_contact_by_email,
    get_portal_grant_file,
    get_grant_for_contact,
    get_portal_access_by_code,
    grant_folder_display_name,
    grant_is_active,
    issue_portal_login_otp,
    list_active_grants_for_contact,
    list_grant_files,
    normalize_access_code,
    portal_access_is_active,
    record_portal_auth_failure,
    record_portal_auth_success,
    relative_folder_under_grant,
    verify_portal_login_otp,
)
from app.quote_portal_service import (
    get_delivery_for_contact,
    get_quote_delivery_file_for_contact,
    list_pending_approvals_for_grant,
    list_pending_quote_deliveries_for_contact,
    portal_quote_delivery_view,
    respond_to_quote_delivery,
)
from app.docusign_signing_service import (
    create_signing_redirect_url,
    list_pending_for_contact,
    portal_signing_view,
    sync_envelope_status,
)
from app.portal_form_service import (
    complete_submission,
    get_submission_for_contact,
    list_pending_for_contact as list_pending_forms_for_contact,
    portal_form_detail,
    upload_submission_file,
)
from app.models import DocusignSigningRequest, PortalFormSubmissionStatus
from app.schemas import (
    PortalAuthIn,
    PortalAuthOut,
    PortalBrowseOut,
    PortalConfigOut,
    PortalFileOut,
    PortalGrantSummaryOut,
    PortalOtpRequestIn,
    PortalOtpVerifyIn,
    PortalPreviewExchangeIn,
    PortalQuoteDeliveryViewOut,
    PortalQuoteExchangeIn,
    PortalQuoteExchangeOut,
    PortalQuoteRespondIn,
    PortalSessionOut,
    PortalDocusignSigningOut,
    PortalFormDetailOut,
    PortalFormPendingOut,
    PortalFormSubmitIn,
    PortalFormSubmissionOut,
)
from app.alert_dispatch import AlertKind, dispatch_alert, portal_public_url
from app.security import (
    create_portal_session_token,
    decode_portal_preview_exchange_token,
    decode_portal_quote_exchange_token,
)

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
    grants = filter_grants_for_portal_enabled_cases(db, list_active_grants_for_contact(db, contact_id))
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
    return PortalConfigOut(firm_name=name)


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


@router.post("/auth/request-otp", status_code=status.HTTP_204_NO_CONTENT)
def portal_request_otp(payload: PortalOtpRequestIn, db: Session = Depends(get_db)) -> None:
    """Send a one-time sign-in code if this e-mail has active portal access."""
    contact = find_portal_contact_by_email(db, payload.email)
    if contact is None:
        return
    code = issue_portal_login_otp(db, contact.id)
    db.commit()
    dispatch_alert(
        db,
        AlertKind.portal_login_otp,
        to_email=contact.email or "",
        context={
            "contact_name": contact_display_name(contact),
            "otp_code": code,
            "portal_url": portal_public_url(),
        },
    )


@router.post("/auth/verify-otp", response_model=PortalAuthOut)
def portal_verify_otp(payload: PortalOtpVerifyIn, db: Session = Depends(get_db)) -> PortalAuthOut:
    contact = find_portal_contact_by_email(db, payload.email)
    if contact is None or not verify_portal_login_otp(db, contact.id, payload.code.strip()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired sign-in code")
    grants = list_active_grants_for_contact(db, contact.id)
    if not grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No document areas are available for this access code")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access_row:
        record_portal_auth_success(db, access_row)
    db.commit()
    token = create_portal_session_token(contact_id=str(contact.id))
    log_event(
        db,
        actor_user_id=None,
        action="portal.auth.otp",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"contact_id": str(contact.id)},
    )
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
    )


@router.post("/auth/preview-exchange", response_model=PortalAuthOut)
def portal_preview_exchange(payload: PortalPreviewExchangeIn, db: Session = Depends(get_db)) -> PortalAuthOut:
    """Exchange a short-lived staff-issued preview token for a client portal session."""
    try:
        preview = decode_portal_preview_exchange_token(payload.exchange_token.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        contact_id = uuid.UUID(preview.contact_id)
        case_id = uuid.UUID(preview.case_id)
        staff_user_id = uuid.UUID(preview.staff_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid preview link") from exc

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid preview link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active for this contact")
    grants = list_active_grants_for_contact(db, contact_id)
    if not grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No document areas are available for this contact")
    case_grants = [g for g in grants if g.case_id == case_id and grant_is_active(g)]
    if not case_grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No shared folders on this matter for this contact")

    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, case_id)
    token = create_portal_session_token(contact_id=str(contact.id))
    log_event(
        db,
        actor_user_id=staff_user_id,
        action="portal.preview.exchange",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"case_id": str(case_id), "contact_id": str(contact.id)},
    )
    db.commit()
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
    )


def _quote_delivery_view(db: Session, delivery: QuotePortalDelivery) -> PortalQuoteDeliveryViewOut:
    grant = db.get(ContactPortalGrant, delivery.grant_id) if delivery.grant_id else None
    return PortalQuoteDeliveryViewOut(**portal_quote_delivery_view(db, delivery, grant=grant))


@router.post("/quote-exchange", response_model=PortalQuoteExchangeOut)
def portal_quote_exchange(payload: PortalQuoteExchangeIn, db: Session = Depends(get_db)) -> PortalQuoteExchangeOut:
    """Exchange a quote e-mail link for a portal session and quote details."""
    try:
        exchange = decode_portal_quote_exchange_token(payload.exchange_token.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired quote link") from exc
    try:
        contact_id = uuid.UUID(exchange.contact_id)
        case_id = uuid.UUID(exchange.case_id)
        file_id = uuid.UUID(exchange.file_id)
        delivery_id = uuid.UUID(exchange.delivery_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid quote link") from exc

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid quote link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")
    delivery = db.get(QuotePortalDelivery, delivery_id)
    if (
        delivery is None
        or delivery.contact_id != contact_id
        or delivery.case_id != case_id
        or delivery.file_id != file_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, case_id)

    token = create_portal_session_token(contact_id=str(contact.id))
    log_event(
        db,
        actor_user_id=None,
        action="portal.quote.exchange",
        entity_type="quote_portal_delivery",
        entity_id=str(delivery.id),
        meta={"case_id": str(case_id), "file_id": str(file_id), "contact_id": str(contact_id)},
    )
    db.commit()
    return PortalQuoteExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
        quote=_quote_delivery_view(db, delivery),
    )


@router.get("/quote-deliveries", response_model=list[PortalQuoteDeliveryViewOut])
def portal_list_quote_deliveries(
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> list[PortalQuoteDeliveryViewOut]:
    """Pending quotes for this contact (folder grants not required)."""
    rows = list_pending_quote_deliveries_for_contact(db, contact_id=contact.id)
    return [_quote_delivery_view(db, d) for d in rows]


@router.get("/quote-deliveries/{delivery_id}", response_model=PortalQuoteDeliveryViewOut)
def portal_get_quote_delivery(
    delivery_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalQuoteDeliveryViewOut:
    delivery = get_delivery_for_contact(db, delivery_id, contact.id)
    return _quote_delivery_view(db, delivery)


@router.post("/quote-deliveries/{delivery_id}/respond", response_model=PortalQuoteDeliveryViewOut)
def portal_respond_quote_delivery(
    delivery_id: uuid.UUID,
    payload: PortalQuoteRespondIn,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalQuoteDeliveryViewOut:
    delivery = get_delivery_for_contact(db, delivery_id, contact.id)
    updated = respond_to_quote_delivery(
        db,
        delivery=delivery,
        contact=contact,
        accepted=bool(payload.accepted),
        decline_reason=payload.decline_reason,
    )
    return _quote_delivery_view(db, updated)


@router.get("/quote-deliveries/{delivery_id}/file")
def portal_download_quote_delivery_file(
    delivery_id: uuid.UUID,
    download: bool = Query(default=False),
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
):
    """Download or open a quote file (delivery-scoped; no folder grant required)."""
    delivery, row = get_quote_delivery_file_for_contact(
        db,
        delivery_id=delivery_id,
        contact_id=contact.id,
    )
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not str(abs_path).startswith(str(FILES_ROOT)) or not abs_path.exists():
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
        content_disposition_type="attachment" if download else "inline",
    )


def _file_out(grant: ContactPortalGrant, row: File) -> PortalFileOut:
    rel = relative_folder_under_grant(grant_folder=grant.folder_path or "", absolute_folder=row.folder_path or "")
    display = rel.split("/")[-1] if rel else (row.folder_path or "Documents")
    if rel and "/" in rel:
        display = rel
    elif rel:
        display = rel
    else:
        display = ""
    return PortalFileOut(
        id=row.id,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        folder_path=row.folder_path or "",
        folder_display=display,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/session", response_model=PortalSessionOut)
def portal_session(contact: Contact = Depends(get_portal_contact), db: Session = Depends(get_db)) -> PortalSessionOut:
    grants = list_active_grants_for_contact(db, contact.id)
    if not grants:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No document areas are available")
    return PortalSessionOut(contact_name=contact_display_name(contact), grants=_grant_summaries(db, contact.id))


@router.get("/grants/{grant_id}/browse", response_model=PortalBrowseOut)
def portal_browse_grant(
    grant_id: uuid.UUID,
    subfolder: str = Query(default=""),
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalBrowseOut:
    grant = get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    if not grant.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Download is not allowed for this area")
    rel, child_names, files_here = browse_grant_folder(db, grant, subfolder=subfolder)
    pending = list_pending_approvals_for_grant(db, contact_id=contact.id, grant=grant)
    pending_ids = {d.file_id for d in pending}
    crumbs: list[str] = []
    if rel:
        crumbs = rel.split("/")
    return PortalBrowseOut(
        subfolder=rel,
        breadcrumb=crumbs,
        subfolders=child_names,
        files=[_file_out(grant, f) for f in files_here if f.id not in pending_ids],
        pending_approvals=[PortalQuoteDeliveryViewOut(**portal_quote_delivery_view(db, d, grant=grant)) for d in pending],
        pending_docusign_signings=[
            PortalDocusignSigningOut(**portal_signing_view(db, req, contact_id=contact.id))
            for req, _recip in list_pending_for_contact(db, contact.id)
        ],
        pending_portal_forms=_pending_forms_for_grant(db, contact=contact, grant=grant),
    )


def _pending_forms_for_grant(db: Session, *, contact: Contact, grant: ContactPortalGrant) -> list[PortalFormPendingOut]:
    out: list[PortalFormPendingOut] = []
    for sub in list_pending_forms_for_contact(db, contact.id):
        if sub.case_id != grant.case_id:
            continue
        detail = portal_form_detail(db, sub)
        case = db.get(Case, sub.case_id)
        label = ""
        if case:
            label = " — ".join(p for p in [case.case_number, case.client_name] if p)
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


@router.get("/forms", response_model=list[PortalFormPendingOut])
def portal_list_forms(
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> list[PortalFormPendingOut]:
    out: list[PortalFormPendingOut] = []
    for sub in list_pending_forms_for_contact(db, contact.id):
        detail = portal_form_detail(db, sub)
        case = db.get(Case, sub.case_id)
        label = ""
        if case:
            label = " — ".join(p for p in [case.case_number, case.client_name] if p)
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


@router.get("/forms/{submission_id}", response_model=PortalFormDetailOut)
def portal_get_form(
    submission_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalFormDetailOut:
    sub = get_submission_for_contact(db, submission_id, contact.id)
    if sub.status != PortalFormSubmissionStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Form is not pending")
    return PortalFormDetailOut.model_validate(portal_form_detail(db, sub))


@router.post("/forms/{submission_id}/submit", response_model=PortalFormSubmissionOut)
def portal_submit_form(
    submission_id: uuid.UUID,
    payload: PortalFormSubmitIn,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalFormSubmissionOut:
    from app.portal_form_service import submission_out

    sub = get_submission_for_contact(db, submission_id, contact.id)
    updated = complete_submission(db, submission=sub, contact=contact, responses_in=payload.responses or {})
    db.commit()
    db.refresh(updated)
    return PortalFormSubmissionOut.model_validate(submission_out(db, updated))


@router.post("/forms/{submission_id}/upload")
async def portal_upload_form_file(
    submission_id: uuid.UUID,
    field_key: str = Query(..., min_length=1, max_length=80),
    upload: UploadFile = FastAPIFile(...),
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    sub = get_submission_for_contact(db, submission_id, contact.id)
    result = await upload_submission_file(db, submission=sub, field_key=field_key, upload=upload, contact=contact)
    db.commit()
    return result


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
    return [_file_out(grant, f) for f in rows]


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
    row = get_portal_grant_file(db, grant, contact.id, file_id)
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
    return _file_out(grant, row)


@router.get("/signing-requests", response_model=list[PortalDocusignSigningOut])
def portal_list_signing_requests(
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> list[PortalDocusignSigningOut]:
    out: list[PortalDocusignSigningOut] = []
    for req, _recip in list_pending_for_contact(db, contact.id):
        sync_envelope_status(db, req)
        if req.status.value != "pending":
            continue
        out.append(PortalDocusignSigningOut(**portal_signing_view(db, req, contact_id=contact.id)))
    return out


class PortalSignStartOut(BaseModel):
    url: str


@router.post("/signing-requests/{request_id}/start", response_model=PortalSignStartOut)
def portal_start_signing(
    request_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> PortalSignStartOut:
    req = db.get(DocusignSigningRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    view = portal_signing_view(db, req, contact_id=contact.id)
    from app.docusign_signing_service import get_recipient_by_sign_token

    recipient = get_recipient_by_sign_token(db, view["sign_token"])
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    url = create_signing_redirect_url(db, recipient)
    return PortalSignStartOut(url=url)
