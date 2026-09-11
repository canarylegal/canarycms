"""Public client portal (access code login, scoped folder browse/upload)."""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File as FastAPIFile, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.audit import log_event
from app.db import get_db
from app.deps import (
    get_portal_contact,
    get_portal_session,
    get_portal_write_contact,
    require_portal_client_audience,
    require_portal_client_write,
    require_portal_not_preview,
)
from app.security import (
    PortalSessionPayload,
    create_portal_file_open_token,
    decode_portal_file_open_token,
)
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root, path_is_under_files_root, stream_upload_to_path, unlink_stored_file
from app.upload_limits import content_disposition_for_mime, max_upload_bytes
from app.models import (
    Case,
    CanarySignRecipient,
    CanarySignRecipientStatus,
    CanarySignRequest,
    CanarySignStatus,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    DocusignSigningRequest,
    File,
    FileCategory,
    FirmSettings,
    PortalFormSubmission,
    PortalFormSubmissionStatus,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.permission_checks import user_may_be_fee_earner
from app.portal_branding import (
    CANARY_LEGAL_SOFTWARE_URL,
    POWERED_BY_LABEL,
    firm_display_name,
    portal_title,
)
from app.portal_activity import log_portal_activity
from app.portal_notifications import notify_portal_staff_client_upload
from app.portal_case import filter_grants_for_portal_enabled_cases
from app.portal_service import (
    portal_session_version,
    browse_grant_folder,
    client_matter_description,
    contact_display_name,
    default_grant_label,
    ensure_upload_folder_allowed,
    find_portal_contact_by_email,
    get_portal_grant_file,
    get_grant_for_contact,
    get_matter_portal_access_by_code,
    get_portal_access_by_code,
    grant_folder_display_name,
    grant_is_active,
    issue_portal_login_otp,
    contact_has_portal_content_on_case,
    list_active_grants_for_contact,
    list_active_grants_for_matter_session,
    list_grant_files,
    matter_portal_access_is_active,
    matter_portal_session_version,
    normalize_access_code,
    portal_access_is_active,
    record_matter_portal_auth_failure,
    record_matter_portal_auth_success,
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
    resolve_quote_exchange_delivery,
    respond_to_quote_delivery,
)
from app.docusign_signing_service import (
    create_signing_redirect_url,
    list_pending_for_contact as list_pending_docusign_for_contact,
    portal_signing_view as docusign_portal_signing_view,
    sync_envelope_status,
)
from app.canary_sign_service import (
    claim_form_lock as canary_claim_form_lock,
    decline_signing as canary_decline_signing,
    get_recipient_by_sign_token as get_canary_recipient_by_sign_token,
    list_for_contact as list_canary_sign_for_contact,
    list_pending_for_contact as list_pending_canary_sign_for_contact,
    portal_signing_view as canary_portal_signing_view,
    read_snapshot_pdf_bytes,
    record_view as canary_record_view,
    save_form_responses as canary_save_form_responses,
    submit_signature as canary_submit_signature,
)
from app.portal_form_service import (
    complete_submission,
    get_submission_for_contact,
    list_pending_for_contact as list_pending_forms_for_contact,
    portal_form_detail,
    resolve_form_exchange_submission,
    upload_submission_file,
)
from app.schemas import (
    PortalAuthIn,
    PortalAuthOut,
    PortalBrowseOut,
    PortalCanarySignDeclineIn,
    PortalCanarySignExchangeIn,
    PortalCanarySignExchangeOut,
    PortalCanarySignFormResponsesIn,
    PortalCanarySignOut,
    PortalCanarySignSubmitIn,
    PortalClientActionItemOut,
    PortalClientActionsOut,
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
    PortalFormExchangeIn,
    PortalFormExchangeOut,
    PortalFormPendingOut,
    PortalFormSubmitIn,
    PortalFormSubmissionOut,
)
from app.alert_dispatch import AlertKind, dispatch_alert, portal_public_url
from app.auth_rate_limit import (
    check_portal_auth_rate_limits,
    check_portal_otp_request_rate_limits,
    check_portal_otp_verify_rate_limits,
    clear_portal_otp_verify_rate_limits,
    record_portal_auth_ip_failure,
    record_portal_otp_request_attempt,
    record_portal_otp_verify_failure,
)
from app.client_ip import client_ip_from_request
from app.security import (
    create_portal_session_token,
    decode_portal_preview_exchange_token,
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


def _grant_summaries(
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


@router.get("/config", response_model=PortalConfigOut)
def portal_config(db: Session = Depends(get_db)) -> PortalConfigOut:
    firm = db.get(FirmSettings, 1)
    name = firm_display_name(firm)
    logo_url = "/portal/logo" if firm and firm.portal_logo_file_id else None
    return PortalConfigOut(
        firm_name=name,
        portal_title=portal_title(firm),
        portal_logo_url=logo_url,
        powered_by_label=POWERED_BY_LABEL,
        powered_by_url=CANARY_LEGAL_SOFTWARE_URL,
    )


@router.get("/logo")
def portal_logo(db: Session = Depends(get_db)) -> FileResponse:
    firm = db.get(FirmSettings, 1)
    if firm is None or not firm.portal_logo_file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal logo not configured")
    frow = db.get(File, firm.portal_logo_file_id)
    if frow is None or frow.category != FileCategory.firm_portal_logo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal logo not configured")
    abs_path = (FILES_ROOT / frow.storage_path).resolve()
    if not abs_path.is_file() or not path_is_under_files_root(abs_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal logo not found")
    media = (frow.mime_type or mimetypes.guess_type(frow.original_filename)[0] or "image/png").split(";", 1)[0]
    return FileResponse(abs_path, media_type=media, filename=frow.original_filename)


@router.post("/auth", response_model=PortalAuthOut)
def portal_auth(payload: PortalAuthIn, request: Request, db: Session = Depends(get_db)) -> PortalAuthOut:
    ip = client_ip_from_request(request)
    check_portal_auth_rate_limits(db, ip=ip)
    code = normalize_access_code(payload.access_code)
    if len(code) < 8:
        record_portal_auth_ip_failure(db, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")

    matter_row = get_matter_portal_access_by_code(db, code)
    if matter_row is not None:
        if not matter_portal_access_is_active(matter_row):
            record_matter_portal_auth_failure(db, matter_row)
            record_portal_auth_ip_failure(db, ip=ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
        contact = db.get(Contact, matter_row.contact_id)
        if contact is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
        from app.portal_case import require_case_portal_enabled

        require_case_portal_enabled(db, matter_row.case_id)
        record_matter_portal_auth_success(db, matter_row)
        token = create_portal_session_token(
            contact_id=str(contact.id),
            session_version=matter_portal_session_version(matter_row),
            audience="exchange",
            case_id=str(matter_row.case_id),
        )
        log_event(
            db,
            actor_user_id=None,
            action="portal.auth.success",
            entity_type="matter_portal_access",
            entity_id=str(matter_row.id),
            meta={"contact_id": str(contact.id), "case_id": str(matter_row.case_id), "audience": "exchange"},
        )
        db.commit()
        return PortalAuthOut(
            session_token=token,
            contact_name=contact_display_name(contact),
            grants=_grant_summaries(db, contact.id, case_id=matter_row.case_id),
            focus_case_id=matter_row.case_id,
            staff_preview=False,
            audience="exchange",
        )

    row = get_portal_access_by_code(db, code)
    if row is None or not portal_access_is_active(row):
        if row is not None:
            record_portal_auth_failure(db, row)
        record_portal_auth_ip_failure(db, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    contact = db.get(Contact, row.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code")
    # Valid access code is enough to sign in; empty portal home is allowed (soft empty state).
    record_portal_auth_success(db, row)
    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(row),
        audience="client",
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.auth.success",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"contact_id": str(contact.id), "audience": "client"},
    )
    db.commit()
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
        staff_preview=False,
        audience="client",
    )


@router.post("/auth/request-otp", status_code=status.HTTP_204_NO_CONTENT)
def portal_request_otp(payload: PortalOtpRequestIn, request: Request, db: Session = Depends(get_db)) -> None:
    """Send a one-time sign-in code if this e-mail has active portal access."""
    ip = client_ip_from_request(request)
    email = (payload.email or "").strip().lower()
    check_portal_otp_request_rate_limits(db, email=email, ip=ip)
    record_portal_otp_request_attempt(db, email=email, ip=ip)
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
def portal_verify_otp(payload: PortalOtpVerifyIn, request: Request, db: Session = Depends(get_db)) -> PortalAuthOut:
    ip = client_ip_from_request(request)
    email = (payload.email or "").strip().lower()
    check_portal_otp_verify_rate_limits(db, email=email, ip=ip)
    contact = find_portal_contact_by_email(db, payload.email)
    if contact is None or not verify_portal_login_otp(db, contact.id, payload.code.strip()):
        record_portal_otp_verify_failure(db, email=email, ip=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired sign-in code")
    clear_portal_otp_verify_rate_limits(db, email=email)
    # Valid OTP + active portal access is enough; empty portal home is allowed.
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access_row:
        record_portal_auth_success(db, access_row)
    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.auth.otp",
        entity_type="contact",
        entity_id=str(contact.id),
        meta={"contact_id": str(contact.id)},
    )
    db.commit()
    return PortalAuthOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
        audience="client",
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

    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, case_id)
    if not contact_has_portal_content_on_case(db, contact_id=contact_id, case_id=case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No portal content on this matter for this contact",
        )
    token = create_portal_session_token(
        contact_id=str(contact.id),
        staff_preview=True,
        session_version=portal_session_version(access_row),
    )
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
        focus_case_id=case_id,
        staff_preview=True,
        audience="client",
    )


def _quote_delivery_view(db: Session, delivery: QuotePortalDelivery) -> PortalQuoteDeliveryViewOut:
    grant = db.get(ContactPortalGrant, delivery.grant_id) if delivery.grant_id else None
    return PortalQuoteDeliveryViewOut(**portal_quote_delivery_view(db, delivery, grant=grant))


@router.post("/quote-exchange", response_model=PortalQuoteExchangeOut)
def portal_quote_exchange(payload: PortalQuoteExchangeIn, db: Session = Depends(get_db)) -> PortalQuoteExchangeOut:
    """Exchange a quote e-mail link for a portal session and quote details."""
    try:
        delivery = resolve_quote_exchange_delivery(db, payload.exchange_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired quote link") from exc

    contact_id = delivery.contact_id
    case_id = delivery.case_id

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid quote link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")

    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, case_id)

    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.quote.exchange",
        entity_type="quote_portal_delivery",
        entity_id=str(delivery.id),
        meta={"case_id": str(case_id), "file_id": str(delivery.file_id), "contact_id": str(contact_id)},
    )
    db.commit()
    return PortalQuoteExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
        quote=_quote_delivery_view(db, delivery),
    )


def _form_pending_out(db: Session, submission: PortalFormSubmission) -> PortalFormPendingOut:
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


@router.post("/form-exchange", response_model=PortalFormExchangeOut)
def portal_form_exchange(payload: PortalFormExchangeIn, db: Session = Depends(get_db)) -> PortalFormExchangeOut:
    """Exchange a form e-mail link for a portal session and open the pending form."""
    try:
        submission = resolve_form_exchange_submission(db, payload.exchange_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired form link") from exc

    contact_id = submission.contact_id
    case_id = submission.case_id

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid form link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")

    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, case_id)

    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.form.exchange",
        entity_type="portal_form_submission",
        entity_id=str(submission.id),
        meta={"case_id": str(case_id), "template_id": str(submission.template_id), "contact_id": str(contact_id)},
    )
    db.commit()
    return PortalFormExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
        form=_form_pending_out(db, submission),
    )


@router.get("/quote-deliveries", response_model=list[PortalQuoteDeliveryViewOut])
def portal_list_quote_deliveries(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> list[PortalQuoteDeliveryViewOut]:
    """Pending quotes for this contact (folder grants not required)."""
    require_portal_client_audience(session)
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
    contact: Contact = Depends(get_portal_write_contact),
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


def _file_out(
    grant: ContactPortalGrant,
    row: File,
    *,
    is_new: bool = False,
) -> PortalFileOut:
    from ..file_storage import decode_folder_path_for_display

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


@router.get("/session", response_model=PortalSessionOut)
def portal_session(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
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
        grants=_grant_summaries(db, contact.id, case_id=case_filter),
        staff_preview=session.staff_preview,
        audience="exchange" if getattr(session, "audience", "client") == "exchange" else "client",
        focus_case_id=focus_case_id,
    )


@router.get("/grants/{grant_id}/browse", response_model=PortalBrowseOut)
def portal_browse_grant(
    grant_id: uuid.UUID,
    subfolder: str = Query(default=""),
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
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
    file_outs = [_file_out(grant, f, is_new=file_is_new_since(f, last_viewed)) for f in visible]
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
        pending_portal_forms=[] if exchange else _pending_forms_for_grant(db, contact=contact, grant=grant),
        new_file_count=sum(1 for f in file_outs if f.is_new),
        last_viewed_at=last_viewed,
    )


@router.post("/grants/{grant_id}/viewed", status_code=status.HTTP_204_NO_CONTENT)
def portal_mark_grant_viewed(
    grant_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> None:
    from app.portal_grant_views import mark_grant_viewed

    get_grant_for_contact(db, contact_id=contact.id, grant_id=grant_id)
    mark_grant_viewed(db, contact_id=contact.id, grant_id=grant_id)
    db.commit()
    return None


def _pending_forms_for_grant(db: Session, *, contact: Contact, grant: ContactPortalGrant) -> list[PortalFormPendingOut]:
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


@router.get("/forms", response_model=list[PortalFormPendingOut])
def portal_list_forms(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> list[PortalFormPendingOut]:
    require_portal_client_audience(session)
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
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalFormSubmissionOut:
    from app.portal_form_service import submission_out

    require_portal_client_write(session)
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
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    from pathlib import Path

    from app.file_storage import unlink_stored_file

    require_portal_client_write(session)
    sub = get_submission_for_contact(db, submission_id, contact.id)
    result = await upload_submission_file(db, submission=sub, field_key=field_key, upload=upload, contact=contact)
    abs_path = result.pop("abs_path", None)
    try:
        db.commit()
    except Exception:
        if abs_path:
            unlink_stored_file(Path(abs_path))
        raise
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
                if not path_is_under_files_root(abs_path) or not abs_path.is_file():
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
        db.commit()
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


@router.post("/grants/{grant_id}/files/{file_id}/open-token")
def portal_issue_file_open_token(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Mint a short-lived token so the browser can open the file via a normal navigation URL."""
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


@router.get("/grants/{grant_id}/files/{file_id}/open")
def portal_open_file_with_token(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    token: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Serve the file inline so the browser applies its normal content-type handling (no blob: URL)."""
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


@router.post("/grants/{grant_id}/files", response_model=PortalFileOut, status_code=status.HTTP_201_CREATED)
def portal_upload_file(
    grant_id: uuid.UUID,
    upload: UploadFile = FastAPIFile(...),
    folder: str = Form(default=""),
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalFileOut:
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
    return _file_out(grant, row)


@router.get("/signing-requests", response_model=list[PortalDocusignSigningOut])
def portal_list_signing_requests(
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> list[PortalDocusignSigningOut]:
    out: list[PortalDocusignSigningOut] = []
    for req, _recip in list_pending_docusign_for_contact(db, contact.id):
        sync_envelope_status(db, req)
        if req.status.value != "pending":
            continue
        out.append(PortalDocusignSigningOut(**docusign_portal_signing_view(db, req, contact_id=contact.id)))
    return out


class PortalSignStartOut(BaseModel):
    url: str


@router.post("/signing-requests/{request_id}/start", response_model=PortalSignStartOut)
def portal_start_signing(
    request_id: uuid.UUID,
    contact: Contact = Depends(get_portal_write_contact),
    db: Session = Depends(get_db),
) -> PortalSignStartOut:
    req = db.get(DocusignSigningRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    view = docusign_portal_signing_view(db, req, contact_id=contact.id)
    from app.docusign_signing_service import get_recipient_by_sign_token

    recipient = get_recipient_by_sign_token(db, view["sign_token"])
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")
    url = create_signing_redirect_url(db, recipient)
    return PortalSignStartOut(url=url)


def _canary_request_for_contact(
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


@router.post("/canary-sign-exchange", response_model=PortalCanarySignExchangeOut)
def portal_canary_sign_exchange(
    payload: PortalCanarySignExchangeIn,
    db: Session = Depends(get_db),
) -> PortalCanarySignExchangeOut:
    """Exchange a Canary Sign e-mail link token for a portal session and signing view."""
    recipient = get_canary_recipient_by_sign_token(db, payload.sign_token)
    if recipient is None or not recipient.contact_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired signing link")
    req = db.get(CanarySignRequest, recipient.signing_request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired signing link")

    contact = db.get(Contact, recipient.contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signing link")
    access_row = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact.id)
    ).scalar_one_or_none()
    if access_row is None or not portal_access_is_active(access_row):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal access is not active")

    from app.portal_case import require_case_portal_enabled

    require_case_portal_enabled(db, req.case_id)

    token = create_portal_session_token(
        contact_id=str(contact.id),
        session_version=portal_session_version(access_row),
    )
    log_event(
        db,
        actor_user_id=None,
        action="portal.canary_sign.exchange",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "contact_id": str(contact.id)},
    )
    db.commit()
    view = canary_portal_signing_view(db, req, recipient=recipient)
    return PortalCanarySignExchangeOut(
        session_token=token,
        contact_name=contact_display_name(contact),
        grants=_grant_summaries(db, contact.id),
        signing=PortalCanarySignOut(**view),
    )


@router.get("/canary-sign", response_model=list[PortalCanarySignOut])
def portal_list_canary_sign(
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> list[PortalCanarySignOut]:
    return [
        PortalCanarySignOut(**canary_portal_signing_view(db, req, recipient=recip))
        for req, recip in list_canary_sign_for_contact(db, contact.id)
    ]


@router.get("/canary-sign/{request_id}", response_model=PortalCanarySignOut)
def portal_get_canary_sign(
    request_id: uuid.UUID,
    request: Request,
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalCanarySignOut:
    req, recip = _canary_request_for_contact(db, request_id, contact.id)
    if not session.staff_preview:
        ip = client_ip_from_request(request)
        ua = request.headers.get("user-agent")
        canary_record_view(db, req, recip, ip=ip, ua=ua)
    return PortalCanarySignOut(**canary_portal_signing_view(db, req, recipient=recip))


@router.get("/canary-sign/{request_id}/pdf")
def portal_canary_sign_pdf(
    request_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
):
    req, _recip = _canary_request_for_contact(db, request_id, contact.id)
    raw = read_snapshot_pdf_bytes(db, req)
    filename = f"{(req.subject or 'document')[:80]}.pdf"
    return Response(
        content=raw,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/canary-sign/{request_id}/form/lock", response_model=PortalCanarySignOut)
def portal_canary_sign_form_lock(
    request_id: uuid.UUID,
    request: Request,
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalCanarySignOut:
    require_portal_client_write(session)
    req, recip = _canary_request_for_contact(db, request_id, contact.id)
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")
    updated = canary_claim_form_lock(db, req, recip, ip=ip, ua=ua)
    return PortalCanarySignOut(**canary_portal_signing_view(db, updated, contact_id=contact.id))


@router.put("/canary-sign/{request_id}/form/responses", response_model=PortalCanarySignOut)
def portal_canary_sign_form_responses(
    request_id: uuid.UUID,
    payload: PortalCanarySignFormResponsesIn,
    request: Request,
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalCanarySignOut:
    require_portal_client_write(session)
    req, recip = _canary_request_for_contact(db, request_id, contact.id)
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")
    updated = canary_save_form_responses(
        db,
        req,
        recip,
        payload.responses or {},
        ip=ip,
        ua=ua,
    )
    return PortalCanarySignOut(**canary_portal_signing_view(db, updated, contact_id=contact.id))


@router.post("/canary-sign/{request_id}/sign", response_model=PortalCanarySignOut)
def portal_canary_sign_submit(
    request_id: uuid.UUID,
    payload: PortalCanarySignSubmitIn,
    request: Request,
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalCanarySignOut:
    require_portal_client_write(session)
    req, recip = _canary_request_for_contact(db, request_id, contact.id)
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")
    updated = canary_submit_signature(
        db,
        req,
        recip,
        field_values=payload.field_values or {},
        form_responses=payload.form_responses,
        ip=ip,
        ua=ua,
        consent=bool(payload.consent),
    )
    return PortalCanarySignOut(**canary_portal_signing_view(db, updated, contact_id=contact.id))


@router.post("/canary-sign/{request_id}/decline", response_model=PortalCanarySignOut)
def portal_canary_sign_decline(
    request_id: uuid.UUID,
    payload: PortalCanarySignDeclineIn,
    request: Request,
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalCanarySignOut:
    require_portal_client_write(session)
    req, recip = _canary_request_for_contact(db, request_id, contact.id)
    ip = client_ip_from_request(request)
    ua = request.headers.get("user-agent")
    updated = canary_decline_signing(
        db,
        req,
        recip,
        reason=(payload.reason or "").strip(),
        ip=ip,
        ua=ua,
    )
    return PortalCanarySignOut(**canary_portal_signing_view(db, updated, contact_id=contact.id))


@router.get("/client-actions", response_model=PortalClientActionsOut)
def portal_client_actions(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalClientActionsOut:
    """Unified outstanding / complete / inactive action items for the portal home."""
    require_portal_client_audience(session)
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

    # Quotes complete / inactive for this contact
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
                title=_form_pending_out(db, sub).template_name or "Form",
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
            title=_form_pending_out(db, sub).template_name or "Form",
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
