"""Public client portal (access code login, scoped folder browse/upload)."""

from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, File as FastAPIFile, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    get_portal_contact,
    get_portal_session,
    get_portal_write_contact,
    require_portal_client_audience,
    require_portal_client_write,
)
from app.file_storage import FILES_ROOT, path_is_under_files_root
from app.models import (
    Contact,
    DocusignSigningRequest,
    File,
    FileCategory,
    FirmSettings,
    PortalFormSubmissionStatus,
)
from app.portal_branding import (
    CANARY_LEGAL_SOFTWARE_URL,
    POWERED_BY_LABEL,
    firm_display_name,
    portal_title,
)
from app.portal_auth_service import (
    portal_auth as portal_auth_service,
    portal_canary_sign_exchange as portal_canary_sign_exchange_service,
    portal_form_exchange as portal_form_exchange_service,
    portal_preview_exchange as portal_preview_exchange_service,
    portal_quote_exchange as portal_quote_exchange_service,
    portal_request_otp as portal_request_otp_service,
    portal_verify_otp as portal_verify_otp_service,
)
from app.portal_browse_service import (
    browse_grant as browse_grant_service,
    canary_request_for_contact,
    canary_sign_pdf as canary_sign_pdf_service,
    client_actions as client_actions_service,
    download_file as download_file_service,
    download_grant_zip as download_grant_zip_service,
    download_quote_delivery_file as download_quote_delivery_file_service,
    file_out as _file_out,  # noqa: F401 — re-export
    form_pending_out as _form_pending_out,  # noqa: F401 — re-export
    grant_summaries as _grant_summaries,  # noqa: F401 — re-export
    issue_file_open_token as issue_file_open_token_service,
    list_files as list_files_service,
    list_forms as list_forms_service,
    open_file_with_token as open_file_with_token_service,
    pending_forms_for_grant as _pending_forms_for_grant,  # noqa: F401 — re-export
    portal_session as portal_session_service,
    quote_delivery_view as _quote_delivery_view,
    safe_zip_name as _safe_zip_name,  # noqa: F401 — re-export
    unlink_if_exists as _unlink_if_exists,  # noqa: F401 — re-export
    upload_file as upload_file_service,
)
from app.quote_portal_service import (
    get_delivery_for_contact,
    list_pending_quote_deliveries_for_contact,
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
    list_for_contact as list_canary_sign_for_contact,
    portal_signing_view as canary_portal_signing_view,
    record_view as canary_record_view,
    save_form_responses as canary_save_form_responses,
    submit_signature as canary_submit_signature,
)
from app.portal_form_service import (
    complete_submission,
    get_submission_for_contact,
    portal_form_detail,
    upload_submission_file,
)
from app.portal_service import get_grant_for_contact
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
    PortalClientActionsOut,
    PortalConfigOut,
    PortalFileOut,
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
from app.client_ip import client_ip_from_request
from app.security import PortalSessionPayload

# Alias for canary helper re-export (tests / callers may use underscore name).
_canary_request_for_contact = canary_request_for_contact  # noqa: F401

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/config", response_model=PortalConfigOut)
def portal_config(db: Session = Depends(get_db)) -> PortalConfigOut:
    from app.portal_background import portal_background_color

    firm = db.get(FirmSettings, 1)
    name = firm_display_name(firm)
    logo_url = "/portal/logo" if firm and firm.portal_logo_file_id else None
    return PortalConfigOut(
        firm_name=name,
        portal_title=portal_title(firm),
        portal_logo_url=logo_url,
        portal_background_color=portal_background_color(firm),
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
    return portal_auth_service(payload, request, db)


@router.post("/auth/request-otp", status_code=status.HTTP_204_NO_CONTENT)
def portal_request_otp(payload: PortalOtpRequestIn, request: Request, db: Session = Depends(get_db)) -> None:
    return portal_request_otp_service(payload, request, db)


@router.post("/auth/verify-otp", response_model=PortalAuthOut)
def portal_verify_otp(payload: PortalOtpVerifyIn, request: Request, db: Session = Depends(get_db)) -> PortalAuthOut:
    return portal_verify_otp_service(payload, request, db)


@router.post("/auth/preview-exchange", response_model=PortalAuthOut)
def portal_preview_exchange(payload: PortalPreviewExchangeIn, db: Session = Depends(get_db)) -> PortalAuthOut:
    return portal_preview_exchange_service(payload, db)


@router.post("/quote-exchange", response_model=PortalQuoteExchangeOut)
def portal_quote_exchange(payload: PortalQuoteExchangeIn, db: Session = Depends(get_db)) -> PortalQuoteExchangeOut:
    return portal_quote_exchange_service(payload, db)


@router.post("/form-exchange", response_model=PortalFormExchangeOut)
def portal_form_exchange(payload: PortalFormExchangeIn, db: Session = Depends(get_db)) -> PortalFormExchangeOut:
    return portal_form_exchange_service(payload, db)


@router.get("/quote-deliveries", response_model=list[PortalQuoteDeliveryViewOut])
def portal_list_quote_deliveries(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> list[PortalQuoteDeliveryViewOut]:
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
    return download_quote_delivery_file_service(
        delivery_id, download=download, contact=contact, db=db
    )


@router.get("/session", response_model=PortalSessionOut)
def portal_session(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalSessionOut:
    return portal_session_service(contact, session, db)


@router.get("/grants/{grant_id}/browse", response_model=PortalBrowseOut)
def portal_browse_grant(
    grant_id: uuid.UUID,
    subfolder: str = Query(default=""),
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalBrowseOut:
    return browse_grant_service(
        grant_id, subfolder=subfolder, contact=contact, session=session, db=db
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


@router.get("/forms", response_model=list[PortalFormPendingOut])
def portal_list_forms(
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> list[PortalFormPendingOut]:
    require_portal_client_audience(session)
    return list_forms_service(contact, db)


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
    return list_files_service(grant_id, contact, db)


@router.get("/grants/{grant_id}/files/download-zip")
def portal_download_grant_zip(
    grant_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
):
    return download_grant_zip_service(grant_id, contact, db)


@router.get("/grants/{grant_id}/files/{file_id}")
def portal_download_file(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    download: bool = Query(default=False),
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
):
    return download_file_service(grant_id, file_id, download=download, contact=contact, db=db)


@router.post("/grants/{grant_id}/files/{file_id}/open-token")
def portal_issue_file_open_token(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    contact: Contact = Depends(get_portal_contact),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    return issue_file_open_token_service(grant_id, file_id, contact, db)


@router.get("/grants/{grant_id}/files/{file_id}/open")
def portal_open_file_with_token(
    grant_id: uuid.UUID,
    file_id: uuid.UUID,
    token: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return open_file_with_token_service(grant_id, file_id, token, db)


@router.post("/grants/{grant_id}/files", response_model=PortalFileOut, status_code=status.HTTP_201_CREATED)
def portal_upload_file(
    grant_id: uuid.UUID,
    upload: UploadFile = FastAPIFile(...),
    folder: str = Form(default=""),
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalFileOut:
    return upload_file_service(
        grant_id, upload, folder=folder, contact=contact, session=session, db=db
    )


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


@router.post("/canary-sign-exchange", response_model=PortalCanarySignExchangeOut)
def portal_canary_sign_exchange(
    payload: PortalCanarySignExchangeIn,
    db: Session = Depends(get_db),
) -> PortalCanarySignExchangeOut:
    return portal_canary_sign_exchange_service(payload, db)


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
    req, recip = canary_request_for_contact(db, request_id, contact.id)
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
    return canary_sign_pdf_service(request_id, contact, db)


@router.post("/canary-sign/{request_id}/form/lock", response_model=PortalCanarySignOut)
def portal_canary_sign_form_lock(
    request_id: uuid.UUID,
    request: Request,
    contact: Contact = Depends(get_portal_contact),
    session: PortalSessionPayload = Depends(get_portal_session),
    db: Session = Depends(get_db),
) -> PortalCanarySignOut:
    require_portal_client_write(session)
    req, recip = canary_request_for_contact(db, request_id, contact.id)
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
    req, recip = canary_request_for_contact(db, request_id, contact.id)
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
    req, recip = canary_request_for_contact(db, request_id, contact.id)
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
    req, recip = canary_request_for_contact(db, request_id, contact.id)
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
    require_portal_client_audience(session)
    return client_actions_service(contact, db)
