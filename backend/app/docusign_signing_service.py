"""Send, track, and complete DocuSign signing requests on matters."""

from __future__ import annotations

import logging
import secrets
import uuid
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert, firm_alerts_configured, portal_public_url
from app.deps import get_case_if_accessible
from app.audit import log_event
from app.docusign_client import (
    DocusignApiError,
    create_envelope,
    create_recipient_view,
    download_envelope_document_bytes,
    encode_document_base64,
    file_extension_for_mime,
    get_envelope,
    void_envelope,
)
from app.docusign_settings import docusign_configured, docusign_rsa_private_key, envelope_cost_pence, get_docusign_settings
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root
from app.models import (
    Case,
    CaseContact,
    Contact,
    DocusignDocumentTier,
    DocusignIntegrationSettings,
    DocusignRecipientStatus,
    DocusignSignatureLevel,
    DocusignSigningRecipient,
    DocusignSigningRequest,
    DocusignSigningStatus,
    File as DbFile,
    FileCategory,
    User,
)
from app.ledger_audit import log_ledger_post
from app.ledger_service import post_transaction
from app.portal_notifications import list_portal_staff_recipient_users
from app.schemas import LedgerPostCreate

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_enabled(db: Session) -> DocusignIntegrationSettings:
    row = get_docusign_settings(db)
    if not row.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DocuSign integration is disabled")
    if not docusign_configured(db):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DocuSign is not fully configured")
    return row


def _validate_tier(row: DocusignIntegrationSettings, tier: DocusignDocumentTier) -> None:
    if tier == DocusignDocumentTier.a and not row.allow_tier_a:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DocuSign tier A is not enabled")
    if tier == DocusignDocumentTier.b and not row.allow_tier_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DocuSign tier B is not enabled")
    if tier == DocusignDocumentTier.c and not row.allow_tier_c:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DocuSign tier C is not enabled")


def _validate_signature_level(row: DocusignIntegrationSettings, level: DocusignSignatureLevel) -> None:
    if level == DocusignSignatureLevel.wes and not row.allow_wes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Witnessed e-sign (WES) is not enabled")
    if level == DocusignSignatureLevel.qes and not row.allow_qes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Qualified e-sign (QES) is not enabled")


def _sign_link(sign_token: str) -> str:
    base = portal_public_url().rstrip("/")
    return f"{base}?sign={sign_token}"


def _private_key(db: Session, row: DocusignIntegrationSettings) -> str:
    try:
        return docusign_rsa_private_key(row)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DocuSign private key is invalid") from e


def active_signing_for_file(db: Session, file_id: uuid.UUID) -> DocusignSigningRequest | None:
    return db.execute(
        select(DocusignSigningRequest)
        .where(
            DocusignSigningRequest.source_file_id == file_id,
            DocusignSigningRequest.status == DocusignSigningStatus.pending,
        )
        .order_by(DocusignSigningRequest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def signing_request_file_list_item(req: DocusignSigningRequest) -> dict[str, Any]:
    """Minimal signing payload for matter file lists (no per-row recipient queries)."""
    return {
        "id": str(req.id),
        "case_id": str(req.case_id),
        "source_file_id": str(req.source_file_id) if req.source_file_id else None,
        "status": req.status.value,
        "status_detail": req.status_detail,
    }


def signing_request_out(db: Session, req: DocusignSigningRequest) -> dict[str, Any]:
    recipients = db.execute(
        select(DocusignSigningRecipient)
        .where(DocusignSigningRecipient.signing_request_id == req.id)
        .order_by(DocusignSigningRecipient.routing_order, DocusignSigningRecipient.created_at)
    ).scalars().all()
    source_name = ""
    if req.source_file_id:
        f = db.get(DbFile, req.source_file_id)
        if f:
            source_name = f.original_filename or ""
    return {
        "id": str(req.id),
        "case_id": str(req.case_id),
        "source_file_id": str(req.source_file_id) if req.source_file_id else None,
        "source_filename": source_name,
        "docusign_envelope_id": req.docusign_envelope_id,
        "docusign_template_id": req.docusign_template_id,
        "envelope_subject": req.envelope_subject,
        "document_tier": req.document_tier.value,
        "signature_level": req.signature_level.value,
        "status": req.status.value,
        "status_detail": req.status_detail,
        "signed_file_id": str(req.signed_file_id) if req.signed_file_id else None,
        "certificate_file_id": str(req.certificate_file_id) if req.certificate_file_id else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "voided_at": req.voided_at.isoformat() if req.voided_at else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "recipients": [
            {
                "id": str(r.id),
                "name": r.name,
                "email": r.email,
                "routing_order": r.routing_order,
                "role_name": r.role_name,
                "status": r.status.value,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in recipients
        ],
    }


def _build_envelope_body(
    *,
    subject: str,
    source_file: DbFile | None,
    template_id: str | None,
    recipients: list[DocusignSigningRecipient],
    signature_level: DocusignSignatureLevel,
) -> dict[str, Any]:
    if template_id:
        template_roles = []
        for r in recipients:
            role = {
                "email": r.email,
                "name": r.name,
                "roleName": r.role_name or "Signer",
                "routingOrder": str(r.routing_order),
                "clientUserId": r.client_user_id,
            }
            template_roles.append(role)
        return {
            "emailSubject": subject[:100],
            "templateId": template_id,
            "templateRoles": template_roles,
            "status": "sent",
        }

    if source_file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A document or template is required")

    ensure_files_root()
    abs_path = (FILES_ROOT / source_file.storage_path).resolve()
    if not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file missing on disk")
    raw = abs_path.read_bytes()
    ext = file_extension_for_mime(source_file.mime_type or "", source_file.original_filename or "")
    signers = []
    for idx, r in enumerate(recipients, start=1):
        signer: dict[str, Any] = {
            "email": r.email,
            "name": r.name,
            "recipientId": str(idx),
            "routingOrder": str(r.routing_order),
            "clientUserId": r.client_user_id,
        }
        if signature_level == DocusignSignatureLevel.qes:
            signer["identityVerification"] = {"workflowId": "IDV_PREMIER"}
        signers.append(signer)

    body: dict[str, Any] = {
        "emailSubject": subject[:100],
        "documents": [
            {
                "documentBase64": encode_document_base64(raw),
                "name": Path(source_file.original_filename or "document").stem[:100],
                "fileExtension": ext,
                "documentId": "1",
            }
        ],
        "recipients": {"signers": signers},
        "status": "sent",
    }
    return body


def send_signing_request(
    db: Session,
    *,
    case_id: uuid.UUID,
    actor: User,
    source_file_id: uuid.UUID | None,
    template_id: str | None,
    envelope_subject: str,
    document_tier: DocusignDocumentTier,
    signature_level: DocusignSignatureLevel,
    recipient_specs: list[dict[str, Any]],
    supersedes_id: uuid.UUID | None = None,
) -> DocusignSigningRequest:
    settings = _require_enabled(db)
    _validate_tier(settings, document_tier)
    _validate_signature_level(settings, signature_level)

    if not recipient_specs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one recipient is required")
    if not template_id and not source_file_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a document or a template")

    source_file: DbFile | None = None
    if source_file_id:
        source_file = db.get(DbFile, source_file_id)
        if not source_file or source_file.case_id != case_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if source_file.category == FileCategory.system:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot sign system items")
        existing = active_signing_for_file(db, source_file_id)
        if existing and not supersedes_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document already has a pending DocuSign envelope. Void it or amend and re-send.",
            )

    subject = (envelope_subject or "").strip()
    if not subject:
        subject = source_file.original_filename if source_file else "Please sign"

    req = DocusignSigningRequest(
        id=uuid.uuid4(),
        case_id=case_id,
        source_file_id=source_file_id,
        sent_by_user_id=actor.id,
        supersedes_id=supersedes_id,
        docusign_template_id=template_id,
        envelope_subject=subject,
        document_tier=document_tier,
        signature_level=signature_level,
        status=DocusignSigningStatus.pending,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(req)
    db.flush()

    recipients: list[DocusignSigningRecipient] = []
    for spec in recipient_specs:
        name = str(spec.get("name") or "").strip()
        email = str(spec.get("email") or "").strip().lower()
        if not name or not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each recipient needs a name and email")
        routing_order = int(spec.get("routing_order") or 1)
        role_name = str(spec.get("role_name") or "").strip() or None
        case_contact_id = spec.get("case_contact_id")
        contact_id = spec.get("contact_id")
        cc_uuid = uuid.UUID(str(case_contact_id)) if case_contact_id else None
        c_uuid = uuid.UUID(str(contact_id)) if contact_id else None
        if cc_uuid and not c_uuid:
            cc_row = db.get(CaseContact, cc_uuid)
            if cc_row and cc_row.contact_id:
                c_uuid = cc_row.contact_id
        recipient = DocusignSigningRecipient(
            id=uuid.uuid4(),
            signing_request_id=req.id,
            case_contact_id=cc_uuid,
            contact_id=c_uuid,
            name=name,
            email=email,
            routing_order=max(1, routing_order),
            role_name=role_name,
            client_user_id=secrets.token_urlsafe(16),
            sign_token=secrets.token_urlsafe(24),
            status=DocusignRecipientStatus.pending,
            created_at=utcnow(),
        )
        db.add(recipient)
        recipients.append(recipient)
    db.flush()

    private_key = _private_key(db, settings)
    try:
        envelope_id = create_envelope(
            settings,
            private_key_pem=private_key,
            body=_build_envelope_body(
                subject=subject,
                source_file=source_file,
                template_id=template_id,
                recipients=recipients,
                signature_level=signature_level,
            ),
        )
    except DocusignApiError as e:
        log.warning("DocuSign envelope create failed: %s", e)
        req.status = DocusignSigningStatus.error
        req.status_detail = str(e)
        db.add(req)
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e

    req.docusign_envelope_id = envelope_id
    req.updated_at = utcnow()
    db.add(req)

    if supersedes_id:
        old = db.get(DocusignSigningRequest, supersedes_id)
        if old and old.status == DocusignSigningStatus.pending:
            old.status = DocusignSigningStatus.voided
            old.voided_at = utcnow()
            old.status_detail = "Superseded by amended envelope"
            db.add(old)

    _notify_recipients_sign(db, req, recipients)
    _notify_staff_sent(db, case_id, req, actor)
    _post_docusign_anticipated_charge(
        db,
        case_id=case_id,
        req=req,
        envelope_id=envelope_id,
        settings=settings,
        actor=actor,
    )

    log_event(
        db,
        actor_user_id=actor.id,
        action="docusign.envelope.sent",
        entity_type="docusign_signing_request",
        entity_id=str(req.id),
        meta={"case_id": str(case_id), "envelope_id": envelope_id, "source_file_id": str(source_file_id or "")},
    )
    db.commit()
    db.refresh(req)
    return req


def _month_end(today: date | None = None) -> date:
    d = today or date.today()
    _, last = monthrange(d.year, d.month)
    return date(d.year, d.month, last)


def _post_docusign_anticipated_charge(
    db: Session,
    *,
    case_id: uuid.UUID,
    req: DocusignSigningRequest,
    envelope_id: str,
    settings: DocusignIntegrationSettings,
    actor: User,
) -> None:
    amount = envelope_cost_pence(settings, req.signature_level)
    if amount <= 0:
        return
    case = db.get(Case, case_id)
    matter_ref = (case.case_number if case else "").strip()
    reference = f"{matter_ref} / {envelope_id}".strip(" /")[:200] if matter_ref else envelope_id[:200]
    payload = LedgerPostCreate(
        description=f"DocuSign — {req.envelope_subject[:460]}",
        reference=reference or None,
        amount_pence=amount,
        office_direction="debit",
        anticipated=True,
        anticipated_for_date=_month_end(),
    )
    result = post_transaction(case_id, payload, actor, db)
    req.ledger_pair_id = result.pair_id
    db.add(req)
    log_ledger_post(
        db,
        actor_user_id=actor.id,
        case_id=case_id,
        pair_id=result.pair_id,
        payload=payload,
        is_approved=result.is_approved,
    )


def _notify_recipients_sign(db: Session, req: DocusignSigningRequest, recipients: list[DocusignSigningRecipient]) -> None:
    if not firm_alerts_configured(db):
        return
    case = db.get(Case, req.case_id)
    matter = (case.title if case else "").strip() or "your matter"
    for r in recipients:
        link = _sign_link(r.sign_token)
        dispatch_alert(
            db,
            AlertKind.docusign_sign_requested,
            to_email=r.email,
            context={
                "recipient_name": r.name,
                "document_name": req.envelope_subject,
                "matter_label": matter,
                "sign_url": link,
            },
            actor_user_id=req.sent_by_user_id,
        )


def _notify_staff_sent(db: Session, case_id: uuid.UUID, req: DocusignSigningRequest, actor: User) -> None:
    if not firm_alerts_configured(db):
        return
    for user in list_portal_staff_recipient_users(db, case_id):
        if not user.email:
            continue
        dispatch_alert(
            db,
            AlertKind.docusign_sign_sent_staff,
            to_email=user.email.strip(),
            context={
                "staff_name": user.display_name or user.email,
                "document_name": req.envelope_subject,
                "sender_name": actor.display_name or actor.email,
            },
            actor_user_id=actor.id,
        )


def resend_signing_notifications(db: Session, *, req: DocusignSigningRequest, actor: User) -> None:
    if req.status != DocusignSigningStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending envelopes can be resent")
    recipients = db.execute(
        select(DocusignSigningRecipient).where(DocusignSigningRecipient.signing_request_id == req.id)
    ).scalars().all()
    _notify_recipients_sign(db, req, list(recipients))
    log_event(
        db,
        actor_user_id=actor.id,
        action="docusign.envelope.resent",
        entity_type="docusign_signing_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id)},
    )
    db.commit()


def void_signing_request(
    db: Session,
    *,
    req: DocusignSigningRequest,
    actor: User,
    reason: str,
) -> DocusignSigningRequest:
    if req.status != DocusignSigningStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending envelopes can be voided")
    settings = _require_enabled(db)
    if req.docusign_envelope_id:
        try:
            void_envelope(
                settings,
                private_key_pem=_private_key(db, settings),
                envelope_id=req.docusign_envelope_id,
                reason=reason or "Voided from Canary",
            )
        except DocusignApiError as e:
            log.warning("DocuSign void envelope failed: %s", e)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    req.status = DocusignSigningStatus.voided
    req.voided_at = utcnow()
    req.status_detail = (reason or "Voided")[:500]
    req.updated_at = utcnow()
    db.add(req)
    log_event(
        db,
        actor_user_id=actor.id,
        action="docusign.envelope.voided",
        entity_type="docusign_signing_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "reason": req.status_detail},
    )
    db.commit()
    db.refresh(req)
    return req


def get_recipient_by_sign_token(db: Session, sign_token: str) -> DocusignSigningRecipient | None:
    token = (sign_token or "").strip()
    if not token:
        return None
    return db.execute(
        select(DocusignSigningRecipient).where(DocusignSigningRecipient.sign_token == token).limit(1)
    ).scalar_one_or_none()


def create_signing_redirect_url(db: Session, recipient: DocusignSigningRecipient) -> str:
    req = db.get(DocusignSigningRequest, recipient.signing_request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signing request not found")
    if req.status != DocusignSigningStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This signing request is no longer active")
    if not req.docusign_envelope_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envelope is not ready")

    settings = _require_enabled(db)
    return_url = f"{portal_public_url().rstrip('/')}?signing=complete&token={recipient.sign_token}"
    body = {
        "returnUrl": return_url,
        "authenticationMethod": "none",
        "email": recipient.email,
        "userName": recipient.name,
        "clientUserId": recipient.client_user_id,
    }
    try:
        url = create_recipient_view(
            settings,
            private_key_pem=_private_key(db, settings),
            envelope_id=req.docusign_envelope_id,
            body=body,
        )
    except DocusignApiError as e:
        log.warning("DocuSign recipient view failed: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    recipient.status = DocusignRecipientStatus.sent
    db.add(recipient)
    db.commit()
    return url


def _save_case_file(
    db: Session,
    *,
    case_id: uuid.UUID,
    owner_id: uuid.UUID,
    folder_path: str,
    filename: str,
    mime_type: str,
    raw: bytes,
) -> DbFile:
    ensure_files_root()
    file_id = uuid.uuid4()
    paths = case_file_paths(
        case_id=case_id,
        file_id=file_id,
        original_filename=filename,
        folder_path=folder_path,
    )
    paths.abs_path.parent.mkdir(parents=True, exist_ok=True)
    paths.abs_path.write_bytes(raw)
    now = utcnow()
    row = DbFile(
        id=file_id,
        case_id=case_id,
        owner_id=owner_id,
        category=FileCategory.case_document,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(raw),
        version=1,
        is_pinned=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def complete_signing_request(db: Session, req: DocusignSigningRequest, *, detail: str | None = None) -> None:
    if req.status == DocusignSigningStatus.completed:
        return
    if not req.docusign_envelope_id:
        return
    settings = get_docusign_settings(db)
    if not docusign_configured(db):
        return
    private_key = docusign_rsa_private_key(settings)
    source = db.get(DbFile, req.source_file_id) if req.source_file_id else None
    folder_path = (source.folder_path if source else "") or ""
    owner_id = req.sent_by_user_id or (source.owner_id if source else None)
    if owner_id is None:
        return

    try:
        combined = download_envelope_document_bytes(
            settings, private_key_pem=private_key, envelope_id=req.docusign_envelope_id, document_id="combined"
        )
        cert = download_envelope_document_bytes(
            settings, private_key_pem=private_key, envelope_id=req.docusign_envelope_id, document_id="certificate"
        )
    except DocusignApiError as e:
        log.warning("DocuSign download failed for %s: %s", req.id, e)
        req.status = DocusignSigningStatus.error
        req.status_detail = str(e)[:500]
        req.updated_at = utcnow()
        db.add(req)
        db.commit()
        return

    stem = Path(source.original_filename if source else req.envelope_subject).stem or "document"
    signed = _save_case_file(
        db,
        case_id=req.case_id,
        owner_id=owner_id,
        folder_path=folder_path,
        filename=f"{stem} (signed).pdf",
        mime_type="application/pdf",
        raw=combined,
    )
    cert_file = _save_case_file(
        db,
        case_id=req.case_id,
        owner_id=owner_id,
        folder_path=folder_path,
        filename=f"{stem} (DocuSign certificate).pdf",
        mime_type="application/pdf",
        raw=cert,
    )
    req.status = DocusignSigningStatus.completed
    req.signed_file_id = signed.id
    req.certificate_file_id = cert_file.id
    req.completed_at = utcnow()
    req.updated_at = utcnow()
    req.status_detail = detail
    db.add(req)

    recipients = db.execute(
        select(DocusignSigningRecipient).where(DocusignSigningRecipient.signing_request_id == req.id)
    ).scalars().all()
    for r in recipients:
        if r.status != DocusignRecipientStatus.completed:
            r.status = DocusignRecipientStatus.completed
            r.completed_at = utcnow()
            db.add(r)

    log_event(
        db,
        actor_user_id=req.sent_by_user_id,
        action="docusign.envelope.completed",
        entity_type="docusign_signing_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "signed_file_id": str(signed.id)},
    )
    _notify_staff_completed(db, req)
    db.commit()


def _notify_staff_completed(db: Session, req: DocusignSigningRequest) -> None:
    if not firm_alerts_configured(db):
        return
    for user in list_portal_staff_recipient_users(db, req.case_id):
        if not user.email:
            continue
        dispatch_alert(
            db,
            AlertKind.docusign_sign_completed_staff,
            to_email=user.email.strip(),
            context={
                "staff_name": user.display_name or user.email,
                "document_name": req.envelope_subject,
            },
            actor_user_id=req.sent_by_user_id,
        )


def sync_envelope_status(db: Session, req: DocusignSigningRequest) -> DocusignSigningRequest:
    if not req.docusign_envelope_id or req.status != DocusignSigningStatus.pending:
        return req
    settings = get_docusign_settings(db)
    if not docusign_configured(db):
        return req
    try:
        data = get_envelope(
            settings,
            private_key_pem=docusign_rsa_private_key(settings),
            envelope_id=req.docusign_envelope_id,
        )
    except DocusignApiError:
        return req
    env_status = str(data.get("status") or "").lower()
    if env_status == "completed":
        complete_signing_request(db, req)
        db.refresh(req)
    elif env_status == "declined":
        req.status = DocusignSigningStatus.declined
        req.updated_at = utcnow()
        db.add(req)
        db.commit()
        db.refresh(req)
    elif env_status == "voided":
        req.status = DocusignSigningStatus.voided
        req.voided_at = utcnow()
        req.updated_at = utcnow()
        db.add(req)
        db.commit()
        db.refresh(req)
    return req


def list_pending_for_contact(db: Session, contact_id: uuid.UUID) -> list[tuple[DocusignSigningRequest, DocusignSigningRecipient]]:
    rows = db.execute(
        select(DocusignSigningRequest, DocusignSigningRecipient)
        .join(DocusignSigningRecipient, DocusignSigningRecipient.signing_request_id == DocusignSigningRequest.id)
        .where(
            DocusignSigningRecipient.contact_id == contact_id,
            DocusignSigningRequest.status == DocusignSigningStatus.pending,
            DocusignSigningRecipient.status != DocusignRecipientStatus.completed,
        )
        .order_by(DocusignSigningRequest.created_at.desc())
    ).all()
    seen: set[uuid.UUID] = set()
    out: list[tuple[DocusignSigningRequest, DocusignSigningRecipient]] = []
    for req, recip in rows:
        if req.id in seen:
            continue
        seen.add(req.id)
        out.append((req, recip))
    return out


def portal_signing_view(db: Session, req: DocusignSigningRequest, *, contact_id: uuid.UUID) -> dict[str, Any]:
    recipients = db.execute(
        select(DocusignSigningRecipient).where(DocusignSigningRecipient.signing_request_id == req.id)
    ).scalars().all()
    mine = next((r for r in recipients if r.contact_id == contact_id), None)
    if mine is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a recipient on this envelope")
    return {
        "id": str(req.id),
        "envelope_subject": req.envelope_subject,
        "status": req.status.value,
        "can_sign": req.status == DocusignSigningStatus.pending and mine.status != DocusignRecipientStatus.completed,
        "recipient_id": str(mine.id),
        "sign_token": mine.sign_token,
    }


def _recipients_summary(recipients: list[DocusignSigningRecipient]) -> str:
    parts: list[str] = []
    for r in sorted(recipients, key=lambda x: (x.routing_order, x.created_at)):
        label = (r.name or "").strip() or r.email
        if r.email and label.lower() != r.email.lower():
            label = f"{label} ({r.email})"
        elif r.email:
            label = r.email
        if label:
            parts.append(label)
    return "; ".join(parts)


def list_signing_menu_rows(
    db: Session,
    *,
    user: User,
    status_filter: DocusignSigningStatus | None = None,
) -> list[dict[str, Any]]:
    q = (
        select(DocusignSigningRequest, Case)
        .join(Case, DocusignSigningRequest.case_id == Case.id)
        .order_by(DocusignSigningRequest.created_at.desc())
    )
    if status_filter is not None:
        q = q.where(DocusignSigningRequest.status == status_filter)
    rows = db.execute(q).all()
    if not rows:
        return []

    req_ids = [req.id for req, _ in rows]
    recipients = db.execute(
        select(DocusignSigningRecipient).where(DocusignSigningRecipient.signing_request_id.in_(req_ids))
    ).scalars().all()
    recip_by_req: dict[uuid.UUID, list[DocusignSigningRecipient]] = {}
    for r in recipients:
        recip_by_req.setdefault(r.signing_request_id, []).append(r)

    sender_ids = {req.sent_by_user_id for req, _ in rows if req.sent_by_user_id}
    sender_map: dict[uuid.UUID, str] = {}
    if sender_ids:
        for u in db.execute(select(User).where(User.id.in_(sender_ids))).scalars():
            sender_map[u.id] = u.display_name or u.email

    file_ids = {req.source_file_id for req, _ in rows if req.source_file_id}
    file_map: dict[uuid.UUID, str] = {}
    if file_ids:
        for f in db.execute(select(DbFile).where(DbFile.id.in_(file_ids))).scalars():
            file_map[f.id] = f.original_filename or ""

    out: list[dict[str, Any]] = []
    for req, case in rows:
        if get_case_if_accessible(case.id, user, db) is None:
            continue
        recips = recip_by_req.get(req.id, [])
        out.append(
            {
                "id": req.id,
                "case_id": case.id,
                "case_number": case.case_number,
                "client_name": case.client_name,
                "matter_description": case.title or "",
                "envelope_subject": req.envelope_subject,
                "source_filename": file_map.get(req.source_file_id, "") if req.source_file_id else "",
                "status": req.status.value,
                "status_detail": req.status_detail,
                "sent_by_display_name": sender_map.get(req.sent_by_user_id) if req.sent_by_user_id else None,
                "recipients_summary": _recipients_summary(recips),
                "created_at": req.created_at,
                "completed_at": req.completed_at,
                "voided_at": req.voided_at,
            }
        )
    return out


def sync_accessible_pending_signing_requests(db: Session, *, user: User) -> int:
    pending = list_signing_menu_rows(db, user=user, status_filter=DocusignSigningStatus.pending)
    count = 0
    for row in pending:
        req = db.get(DocusignSigningRequest, row["id"])
        if req is None:
            continue
        sync_envelope_status(db, req)
        count += 1
    return count
