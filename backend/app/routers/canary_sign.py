"""Staff Canary Sign (built-in e-sign) routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.canary_sign_pdf import (
    ensure_snapshot_pdf_bytes,
    extract_acroform_fields,
    http_exception_for_pdf_snapshot_failure,
)
from app.canary_sign_service import (
    active_signing_for_file,
    list_case_requests,
    list_signing_menu_rows,
    remind_signing_request,
    send_signing_request,
    signing_request_out,
    void_signing_request,
)
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.download_headers import content_disposition_headers
from app.models import CanarySignOrderMode, CanarySignRequest, CanarySignStatus, FileCategory, User
from app.models import File as DbFile
from app.schemas import (
    CanarySignAcroFormFieldOut,
    CanarySignMenuRowOut,
    CanarySignSendIn,
    CanarySignSigningRequestOut,
    CanarySignStaffOptionsOut,
    CanarySignVoidIn,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["canary-sign"])
case_router = APIRouter(prefix="/cases/{case_id}/canary-sign", tags=["case-canary-sign"])

_STATUS_FILTERS: dict[str, CanarySignStatus] = {
    "pending": CanarySignStatus.pending,
    "completed": CanarySignStatus.completed,
    "declined": CanarySignStatus.declined,
    "voided": CanarySignStatus.voided,
    "expired": CanarySignStatus.expired,
}


@router.get("/canary-sign/options", response_model=CanarySignStaffOptionsOut)
def staff_canary_sign_options(user: User = Depends(get_current_user)) -> CanarySignStaffOptionsOut:
    return CanarySignStaffOptionsOut(enabled=True)


@router.get("/canary-sign/requests", response_model=list[CanarySignMenuRowOut])
def staff_list_canary_sign_requests(
    status: str | None = Query(
        default=None,
        description="Filter by status: pending, completed, declined, voided, expired. Omit for all.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CanarySignMenuRowOut]:
    status_filter: CanarySignStatus | None = None
    if status:
        key = status.strip().lower()
        if key not in ("", "all"):
            status_filter = _STATUS_FILTERS.get(key)
            if status_filter is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter")
    rows = list_signing_menu_rows(db, user=user, status_filter=status_filter)
    return [CanarySignMenuRowOut(**r) for r in rows]


@case_router.get("/files/{file_id}/active", response_model=CanarySignSigningRequestOut | None)
def get_active_canary_signing_for_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    req = active_signing_for_file(db, file_id)
    if req is None or req.case_id != case_id:
        return None
    return CanarySignSigningRequestOut(**signing_request_out(db, req))


@case_router.get("/files/{file_id}/preview-pdf")
def get_canary_sign_preview_pdf(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """PDF used for staff field placement before send (pass-through or OnlyOffice convert)."""
    require_case_access(case_id, user, db)
    source = db.get(DbFile, file_id)
    if not source or source.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if source.category == FileCategory.system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot sign system items")
    try:
        raw = ensure_snapshot_pdf_bytes(
            db,
            source,
            user,
            conversion_key=f"canary-sign-preview-{file_id}",
        )
    except Exception as e:
        log.exception("Canary Sign preview PDF failed for file %s", file_id)
        raise http_exception_for_pdf_snapshot_failure(e) from e
    filename = f"{(source.original_filename or 'document')[:80]}.pdf"
    return Response(
        content=raw,
        media_type="application/pdf",
        headers=content_disposition_headers(filename, disposition="inline"),
    )


@case_router.get("/files/{file_id}/form-fields", response_model=list[CanarySignAcroFormFieldOut])
def get_canary_sign_form_fields(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CanarySignAcroFormFieldOut]:
    """Detect AcroForm fields on a source file (for staff send UI)."""
    require_case_access(case_id, user, db)
    source = db.get(DbFile, file_id)
    if not source or source.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    try:
        raw = ensure_snapshot_pdf_bytes(
            db,
            source,
            user,
            conversion_key=f"canary-sign-form-fields-{file_id}",
        )
    except Exception as e:
        log.exception("Canary Sign form-fields PDF failed for file %s", file_id)
        raise http_exception_for_pdf_snapshot_failure(e) from e
    return [CanarySignAcroFormFieldOut(**f) for f in extract_acroform_fields(raw)]


@case_router.get("/requests", response_model=list[CanarySignSigningRequestOut])
def list_case_canary_sign_requests(
    case_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CanarySignSigningRequestOut]:
    require_case_access(case_id, user, db)
    return [CanarySignSigningRequestOut(**signing_request_out(db, r)) for r in list_case_requests(db, case_id)]


@case_router.post("/send", response_model=CanarySignSigningRequestOut, status_code=status.HTTP_201_CREATED)
def post_send_canary_sign(
    case_id: uuid.UUID,
    payload: CanarySignSendIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    order = CanarySignOrderMode(payload.order_mode)
    fields_specs = [f.model_dump() for f in payload.fields]
    req = send_signing_request(
        db,
        case_id=case_id,
        actor=user,
        source_file_id=payload.source_file_id,
        subject=(payload.subject or "").strip(),
        recipient_specs=[r.model_dump() for r in payload.recipients],
        order_mode=order,
        expires_in_days=payload.expires_in_days,
        fields_specs=fields_specs,
        retain_fillable_form=payload.retain_fillable_form,
    )
    return CanarySignSigningRequestOut(**signing_request_out(db, req))


@case_router.post("/requests/{request_id}/void", response_model=CanarySignSigningRequestOut)
def post_void_canary_sign(
    case_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CanarySignVoidIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    req = db.get(CanarySignRequest, request_id)
    if not req or req.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    req = void_signing_request(db, req=req, actor=user, reason=(payload.reason or "").strip())
    return CanarySignSigningRequestOut(**signing_request_out(db, req))


@case_router.post("/requests/{request_id}/remind", status_code=status.HTTP_204_NO_CONTENT)
def post_remind_canary_sign(
    case_id: uuid.UUID,
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    req = db.get(CanarySignRequest, request_id)
    if not req or req.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    remind_signing_request(db, req=req, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@case_router.post("/requests/{request_id}/amend", response_model=CanarySignSigningRequestOut, status_code=status.HTTP_201_CREATED)
def post_amend_canary_sign(
    case_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CanarySignSendIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Amend = void pending (via supersedes) + send a new request."""
    require_case_access(case_id, user, db)
    old = db.get(CanarySignRequest, request_id)
    if not old or old.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    order = CanarySignOrderMode(payload.order_mode)
    fields_specs = [f.model_dump() for f in payload.fields]
    req = send_signing_request(
        db,
        case_id=case_id,
        actor=user,
        source_file_id=payload.source_file_id or old.source_file_id,
        subject=(payload.subject or old.subject or "").strip(),
        recipient_specs=[r.model_dump() for r in payload.recipients],
        order_mode=order,
        expires_in_days=payload.expires_in_days,
        fields_specs=fields_specs,
        supersedes_id=old.id,
        retain_fillable_form=payload.retain_fillable_form,
    )
    return CanarySignSigningRequestOut(**signing_request_out(db, req))
