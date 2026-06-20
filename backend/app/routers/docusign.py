"""Case DocuSign signing and Connect webhook."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.docusign_settings import docusign_connect_hmac_secret, get_docusign_settings
from app.docusign_signing_service import (
    active_signing_for_file,
    create_signing_redirect_url,
    get_recipient_by_sign_token,
    list_signing_menu_rows,
    send_signing_request,
    signing_request_out,
    resend_signing_notifications,
    sync_accessible_pending_signing_requests,
    sync_envelope_status,
    void_signing_request,
)
from app.models import (
    DocusignDocumentTier,
    DocusignSignatureLevel,
    DocusignSigningRequest,
    DocusignSigningStatus,
    User,
)
from app.schemas import (
    DocusignMenuRowOut,
    DocusignSendIn,
    DocusignSigningRequestOut,
    DocusignStaffOptionsOut,
    DocusignVoidIn,
    DocusignTemplateOut,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["docusign"])
case_router = APIRouter(prefix="/cases/{case_id}/docusign", tags=["case-docusign"])


@router.get("/docusign/templates", response_model=list[DocusignTemplateOut])
def staff_list_docusign_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocusignTemplateOut]:
    from app.docusign_client import DocusignApiError, get_template_roles, list_templates
    from app.docusign_settings import docusign_configured, docusign_rsa_private_key, get_docusign_settings

    row = get_docusign_settings(db)
    if not row.enabled or not docusign_configured(db):
        return []
    try:
        private_key = docusign_rsa_private_key(row)
        templates = list_templates(row, private_key_pem=private_key)
    except DocusignApiError as e:
        log.warning("DocuSign template list failed: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    out: list[DocusignTemplateOut] = []
    for t in templates:
        roles: list[str] = []
        try:
            role_rows = get_template_roles(row, private_key_pem=private_key, template_id=t.template_id)
            roles = [r.role_name for r in role_rows]
        except DocusignApiError:
            pass
        out.append(DocusignTemplateOut(template_id=t.template_id, name=t.name, description=t.description, roles=roles))
    return out


@router.get("/docusign/options", response_model=DocusignStaffOptionsOut)
def staff_docusign_options(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocusignStaffOptionsOut:
    row = get_docusign_settings(db)
    return DocusignStaffOptionsOut(
        enabled=bool(row.enabled),
        allow_tier_a=bool(row.allow_tier_a),
        allow_tier_b=bool(row.allow_tier_b),
        allow_tier_c=bool(row.allow_tier_c),
        allow_wes=bool(row.allow_wes),
        allow_qes=bool(row.allow_qes),
    )


_STATUS_FILTERS: dict[str, DocusignSigningStatus] = {
    "pending": DocusignSigningStatus.pending,
    "completed": DocusignSigningStatus.completed,
    "declined": DocusignSigningStatus.declined,
    "voided": DocusignSigningStatus.voided,
    "expired": DocusignSigningStatus.expired,
    "error": DocusignSigningStatus.error,
}


@router.get("/docusign/requests", response_model=list[DocusignMenuRowOut])
def staff_list_docusign_requests(
    status: str | None = Query(
        default=None,
        description="Filter by status: pending, completed, declined, voided, expired, error. Omit for all.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocusignMenuRowOut]:
    row = get_docusign_settings(db)
    if not row.enabled:
        return []
    status_filter: DocusignSigningStatus | None = None
    if status:
        key = status.strip().lower()
        if key not in ("", "all"):
            status_filter = _STATUS_FILTERS.get(key)
            if status_filter is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter")
    rows = list_signing_menu_rows(db, user=user, status_filter=status_filter)
    return [DocusignMenuRowOut(**r) for r in rows]


@router.post("/docusign/requests/sync-pending")
def staff_sync_pending_docusign_requests(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    row = get_docusign_settings(db)
    if not row.enabled:
        return {"synced": 0}
    synced = sync_accessible_pending_signing_requests(db, user=user)
    return {"synced": synced}


@case_router.get("/files/{file_id}/active", response_model=DocusignSigningRequestOut | None)
def get_active_signing_for_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    req = active_signing_for_file(db, file_id)
    if req is None or req.case_id != case_id:
        return None
    sync_envelope_status(db, req)
    return DocusignSigningRequestOut(**signing_request_out(db, req))


@case_router.post("/send", response_model=DocusignSigningRequestOut, status_code=status.HTTP_201_CREATED)
def post_send_for_signature(
    case_id: uuid.UUID,
    payload: DocusignSendIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    tier = DocusignDocumentTier(payload.document_tier)
    level = DocusignSignatureLevel(payload.signature_level)
    recipient_specs = [r.model_dump() for r in payload.recipients]
    req = send_signing_request(
        db,
        case_id=case_id,
        actor=user,
        source_file_id=payload.source_file_id,
        template_id=(payload.template_id or "").strip() or None,
        envelope_subject=(payload.envelope_subject or "").strip(),
        document_tier=tier,
        signature_level=level,
        recipient_specs=recipient_specs,
    )
    return DocusignSigningRequestOut(**signing_request_out(db, req))


@case_router.post("/requests/{request_id}/void", response_model=DocusignSigningRequestOut)
def post_void_signing(
    case_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: DocusignVoidIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    req = db.get(DocusignSigningRequest, request_id)
    if not req or req.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    req = void_signing_request(db, req=req, actor=user, reason=(payload.reason or "").strip())
    return DocusignSigningRequestOut(**signing_request_out(db, req))


@case_router.post("/requests/{request_id}/resend", status_code=status.HTTP_204_NO_CONTENT)
def post_resend_signing(
    case_id: uuid.UUID,
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    req = db.get(DocusignSigningRequest, request_id)
    if not req or req.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    resend_signing_notifications(db, req=req, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@case_router.post("/requests/{request_id}/amend", response_model=DocusignSigningRequestOut, status_code=status.HTTP_201_CREATED)
def post_amend_signing(
    case_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: DocusignSendIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_case_access(case_id, user, db)
    old = db.get(DocusignSigningRequest, request_id)
    if not old or old.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    tier = DocusignDocumentTier(payload.document_tier)
    level = DocusignSignatureLevel(payload.signature_level)
    req = send_signing_request(
        db,
        case_id=case_id,
        actor=user,
        source_file_id=payload.source_file_id or old.source_file_id,
        template_id=(payload.template_id or old.docusign_template_id or "").strip() or None,
        envelope_subject=(payload.envelope_subject or old.envelope_subject or "").strip(),
        document_tier=tier,
        signature_level=level,
        recipient_specs=[r.model_dump() for r in payload.recipients],
        supersedes_id=old.id,
    )
    return DocusignSigningRequestOut(**signing_request_out(db, req))


@router.get("/docusign/sign/{sign_token}")
def public_sign_redirect(sign_token: str, db: Session = Depends(get_db)):
    recipient = get_recipient_by_sign_token(db, sign_token)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired signing link")
    url = create_signing_redirect_url(db, recipient)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/docusign/connect")
async def docusign_connect_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    settings = get_docusign_settings(db)
    secret = docusign_connect_hmac_secret(settings)
    if secret:
        sig = (request.headers.get("X-DocuSign-Signature-1") or "").strip()
        if not sig:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")
        digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
        import base64

        expected = base64.b64encode(digest).decode("ascii")
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {"received": True}

    data = payload.get("data") or payload
    envelope_id = str(data.get("envelopeId") or data.get("envelopeSummary", {}).get("envelopeId") or "").strip()
    if not envelope_id:
        return {"received": True}

    req = db.execute(
        select(DocusignSigningRequest).where(DocusignSigningRequest.docusign_envelope_id == envelope_id).limit(1)
    ).scalar_one_or_none()
    if req is None:
        return {"received": True}

    sync_envelope_status(db, req)
    return {"received": True}
