"""Send, track, and complete Canary Sign (built-in e-sign) requests."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert, firm_alerts_configured, portal_public_url
from app.audit import log_event
from app.canary_sign_pdf import (
    build_audit_certificate_pdf,
    ensure_snapshot_pdf_bytes,
    extract_acroform_fields,
    fill_and_flatten_acroform,
    strip_acroform_fields,
    stamp_from_field_value,
    stamp_signed_pdf,
)
from app.deps import get_case_if_accessible
from app.file_storage import FILES_ROOT, case_file_paths, ensure_files_root, unlink_stored_file, unlink_stored_file
from app.models import (
    CanarySignAuditEvent,
    CanarySignAuditEventType,
    CanarySignField,
    CanarySignFieldType,
    CanarySignOrderMode,
    CanarySignRecipient,
    CanarySignRecipientStatus,
    CanarySignRequest,
    CanarySignStatus,
    Case,
    CaseContact,
    CaseNote,
    File as DbFile,
    FileCategory,
    User,
)
from app.portal_activity import log_portal_activity
from app.portal_case import require_case_portal_enabled
from app.portal_notifications import list_portal_staff_recipient_users
from app.portal_service import client_matter_description, ensure_contact_portal_access_for_delivery

log = logging.getLogger(__name__)

_DEFAULT_EXPIRES_DAYS = 14
_FIELD_TYPES = {t.value: t for t in CanarySignFieldType}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sign_link(sign_token: str) -> str:
    base = portal_public_url().rstrip("/")
    return f"{base}/s/{sign_token}"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def active_signing_for_file(db: Session, file_id: uuid.UUID) -> CanarySignRequest | None:
    return db.execute(
        select(CanarySignRequest)
        .where(
            CanarySignRequest.source_file_id == file_id,
            CanarySignRequest.status == CanarySignStatus.pending,
        )
        .order_by(CanarySignRequest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def signing_request_file_list_item(req: CanarySignRequest) -> dict[str, Any]:
    return {
        "id": str(req.id),
        "case_id": str(req.case_id),
        "source_file_id": str(req.source_file_id) if req.source_file_id else None,
        "status": req.status.value,
        "status_detail": req.status_detail,
    }


def _recipients_for_request(db: Session, request_id: uuid.UUID) -> list[CanarySignRecipient]:
    return list(
        db.execute(
            select(CanarySignRecipient)
            .where(CanarySignRecipient.signing_request_id == request_id)
            .order_by(CanarySignRecipient.routing_order, CanarySignRecipient.created_at)
        )
        .scalars()
        .all()
    )


def _fields_for_request(db: Session, request_id: uuid.UUID) -> list[CanarySignField]:
    return list(
        db.execute(
            select(CanarySignField)
            .where(CanarySignField.signing_request_id == request_id)
            .order_by(CanarySignField.sort_order)
        )
        .scalars()
        .all()
    )


def signing_request_out(db: Session, req: CanarySignRequest) -> dict[str, Any]:
    recipients = _recipients_for_request(db, req.id)
    fields = _fields_for_request(db, req.id)
    source_name = ""
    source = db.get(DbFile, req.source_file_id)
    if source:
        source_name = source.original_filename or ""
    return {
        "id": str(req.id),
        "case_id": str(req.case_id),
        "source_file_id": str(req.source_file_id),
        "source_filename": source_name,
        "snapshot_pdf_file_id": str(req.snapshot_pdf_file_id) if req.snapshot_pdf_file_id else None,
        "signed_file_id": str(req.signed_file_id) if req.signed_file_id else None,
        "certificate_file_id": str(req.certificate_file_id) if req.certificate_file_id else None,
        "subject": req.subject,
        "status": req.status.value,
        "status_detail": req.status_detail,
        "order_mode": req.order_mode.value,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "voided_at": req.voided_at.isoformat() if req.voided_at else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "has_fillable_form": bool(getattr(req, "has_fillable_form", False)),
        "form_locked_by_recipient_id": str(req.form_locked_by_recipient_id)
        if getattr(req, "form_locked_by_recipient_id", None)
        else None,
        "form_completed_at": req.form_completed_at.isoformat()
        if getattr(req, "form_completed_at", None)
        else None,
        "recipients": [
            {
                "id": str(r.id),
                "name": r.name,
                "email": r.email,
                "routing_order": r.routing_order,
                "status": r.status.value,
                "decline_reason": r.decline_reason,
                "signed_at": r.signed_at.isoformat() if r.signed_at else None,
                "viewed_at": r.viewed_at.isoformat() if r.viewed_at else None,
                "contact_id": str(r.contact_id) if r.contact_id else None,
                "case_contact_id": str(r.case_contact_id) if r.case_contact_id else None,
            }
            for r in recipients
        ],
        "fields": [_field_out(f) for f in fields],
    }


def _field_out(f: CanarySignField) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "recipient_id": str(f.recipient_id),
        "field_type": f.field_type.value,
        "label": f.label,
        "required": bool(f.required),
        "sort_order": f.sort_order,
        "placement_mode": f.placement_mode,
        "page": f.page,
        "x_pct": f.x_pct,
        "y_pct": f.y_pct,
        "w_pct": f.w_pct,
        "h_pct": f.h_pct,
        "value": f.value,
        "filled_at": f.filled_at.isoformat() if f.filled_at else None,
    }


def _add_audit(
    db: Session,
    *,
    req: CanarySignRequest,
    event_type: CanarySignAuditEventType,
    recipient_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        CanarySignAuditEvent(
            id=uuid.uuid4(),
            signing_request_id=req.id,
            recipient_id=recipient_id,
            event_type=event_type,
            detail=detail,
            ip=(ip or None) and str(ip)[:64],
            user_agent=(user_agent or None) and str(user_agent)[:500],
            created_at=utcnow(),
        )
    )


def mark_expired_if_needed(db: Session, req: CanarySignRequest) -> CanarySignRequest:
    if req.status != CanarySignStatus.pending:
        return req
    expires = _aware(req.expires_at)
    if expires is None or expires > utcnow():
        return req
    req.status = CanarySignStatus.expired
    req.status_detail = "Expired"
    req.updated_at = utcnow()
    db.add(req)
    _add_audit(db, req=req, event_type=CanarySignAuditEventType.expired, detail={"expires_at": expires.isoformat()})
    db.commit()
    db.refresh(req)
    return req


def _save_case_file(
    db: Session,
    *,
    case_id: uuid.UUID,
    owner_id: uuid.UUID,
    folder_path: str,
    filename: str,
    mime_type: str,
    raw: bytes,
    category: FileCategory = FileCategory.case_document,
    parent_file_id: uuid.UUID | None = None,
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
        category=category,
        storage_path=paths.rel_path,
        folder_path=paths.folder_path,
        parent_file_id=parent_file_id,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(raw),
        version=1,
        is_pinned=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.flush()
    except Exception:
        unlink_stored_file(paths.abs_path)
        raise
    return row


def _parse_field_specs(
    db: Session,
    *,
    request_id: uuid.UUID,
    recipients: list[CanarySignRecipient],
    fields_specs: list[dict[str, Any]] | None,
) -> list[CanarySignField]:
    if not fields_specs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Place at least one field on the document before sending",
        )

    by_id = {str(r.id): r for r in recipients}
    by_order = {r.routing_order: r for r in recipients}
    fields = []
    for idx, spec in enumerate(fields_specs):
        ft_raw = str(spec.get("field_type") or "").strip().lower()
        if ft_raw not in _FIELD_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid field_type: {ft_raw}")
        recip = None
        rid = spec.get("recipient_id")
        if rid:
            recip = by_id.get(str(rid))
        if recip is None and spec.get("routing_order") is not None:
            recip = by_order.get(int(spec["routing_order"]))
        if recip is None and len(recipients) == 1:
            recip = recipients[0]
        if recip is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each field needs a recipient")
        placement = str(spec.get("placement_mode") or "fixed").strip().lower()
        if placement != "fixed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fields must be placed by the sender (placement_mode=fixed)",
            )
        page = spec.get("page")
        x_pct = spec.get("x_pct")
        y_pct = spec.get("y_pct")
        w_pct = spec.get("w_pct")
        h_pct = spec.get("h_pct")
        if page is None or x_pct is None or y_pct is None or w_pct is None or h_pct is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each field requires page, x_pct, y_pct, w_pct, h_pct",
            )
        fields.append(
            CanarySignField(
                id=uuid.uuid4(),
                signing_request_id=request_id,
                recipient_id=recip.id,
                field_type=_FIELD_TYPES[ft_raw],
                label=(str(spec.get("label") or "").strip() or None),
                required=bool(spec.get("required", True)),
                sort_order=int(spec.get("sort_order") if spec.get("sort_order") is not None else idx),
                placement_mode="fixed",
                page=int(page),
                x_pct=float(x_pct),
                y_pct=float(y_pct),
                w_pct=float(w_pct),
                h_pct=float(h_pct),
            )
        )

    for r in recipients:
        theirs = [f for f in fields if f.recipient_id == r.id]
        if not theirs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Place at least one field for signer {r.name or r.email}",
            )
        if not any(f.field_type in (CanarySignFieldType.signature, CanarySignFieldType.initials) for f in theirs):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Place a signature field for signer {r.name or r.email}",
            )
    return fields


def _default_fields_for_recipient(recipient_id: uuid.UUID, request_id: uuid.UUID) -> list[CanarySignField]:
    """Legacy helper retained for tests; new sends require sender-placed fixed fields."""
    specs = [
        (CanarySignFieldType.signature, "Signature", 0),
        (CanarySignFieldType.printed_name, "Printed name", 1),
        (CanarySignFieldType.date, "Date", 2),
    ]
    out: list[CanarySignField] = []
    for ft, label, sort in specs:
        out.append(
            CanarySignField(
                id=uuid.uuid4(),
                signing_request_id=request_id,
                recipient_id=recipient_id,
                field_type=ft,
                label=label,
                required=True,
                sort_order=sort,
                placement_mode="fixed",
                page=1,
                x_pct=10.0,
                y_pct=78.0 + sort * 6,
                w_pct=30.0 if ft == CanarySignFieldType.signature else 28.0,
                h_pct=8.0 if ft == CanarySignFieldType.signature else 5.0,
            )
        )
    return out


def send_signing_request(
    db: Session,
    *,
    case_id: uuid.UUID,
    actor: User,
    source_file_id: uuid.UUID,
    subject: str,
    recipient_specs: list[dict[str, Any]],
    order_mode: CanarySignOrderMode = CanarySignOrderMode.parallel,
    expires_in_days: int = _DEFAULT_EXPIRES_DAYS,
    fields_specs: list[dict[str, Any]] | None = None,
    supersedes_id: uuid.UUID | None = None,
    retain_fillable_form: bool | None = None,
) -> CanarySignRequest:
    require_case_portal_enabled(db, case_id)

    if not recipient_specs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one recipient is required")
    if expires_in_days < 1 or expires_in_days > 365:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expires_in_days must be between 1 and 365")

    source = db.get(DbFile, source_file_id)
    if not source or source.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if source.category == FileCategory.system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot sign system items")
    if getattr(source, "oo_compose_pending", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save and close the document in the editor before sending for signature.",
        )

    existing = active_signing_for_file(db, source_file_id)
    if existing and not supersedes_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document already has a pending Canary Sign request. Void it or amend and re-send.",
        )

    subj = (subject or "").strip() or (source.original_filename or "Please sign")
    now = utcnow()
    req = CanarySignRequest(
        id=uuid.uuid4(),
        case_id=case_id,
        source_file_id=source_file_id,
        sent_by_user_id=actor.id,
        supersedes_id=supersedes_id,
        subject=subj[:500],
        status=CanarySignStatus.pending,
        order_mode=order_mode,
        expires_at=now + timedelta(days=int(expires_in_days)),
        created_at=now,
        updated_at=now,
    )
    db.add(req)
    db.flush()

    # Snapshot PDF (system file)
    try:
        pdf_bytes = ensure_snapshot_pdf_bytes(
            db,
            source,
            actor,
            conversion_key=f"canary-sign-{req.id}",
        )
    except Exception as e:
        log.exception("Canary Sign PDF snapshot failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e).strip() or "Could not prepare PDF for signing",
        ) from e

    detected_fields = extract_acroform_fields(pdf_bytes)
    if detected_fields:
        if retain_fillable_form is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This PDF has fillable form fields. Choose whether to keep them "
                    "(retain_fillable_form=true) or remove them (retain_fillable_form=false)."
                ),
            )
        if retain_fillable_form:
            req.has_fillable_form = True
        else:
            try:
                pdf_bytes = strip_acroform_fields(pdf_bytes)
            except Exception as e:
                log.exception("Failed to strip AcroForm before Canary Sign send")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(e).strip() or "Could not remove fillable form fields from the PDF",
                ) from e
            req.has_fillable_form = bool(extract_acroform_fields(pdf_bytes))
            if req.has_fillable_form:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not fully remove fillable form fields from the PDF",
                )
    else:
        req.has_fillable_form = False

    stem = Path(source.original_filename or "document").stem or "document"
    snapshot = _save_case_file(
        db,
        case_id=case_id,
        owner_id=actor.id,
        folder_path=source.folder_path or "",
        filename=f"{stem} (Canary Sign snapshot).pdf",
        mime_type="application/pdf",
        raw=pdf_bytes,
        category=FileCategory.system,
        parent_file_id=source.id,
    )
    req.snapshot_pdf_file_id = snapshot.id
    db.add(req)

    recipients: list[CanarySignRecipient] = []
    for spec in recipient_specs:
        name = str(spec.get("name") or "").strip()
        email = str(spec.get("email") or "").strip().lower()
        if not name or not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each recipient needs a name and email")
        routing_order = max(1, int(spec.get("routing_order") or 1))
        case_contact_id = spec.get("case_contact_id")
        contact_id = spec.get("contact_id")
        cc_uuid = uuid.UUID(str(case_contact_id)) if case_contact_id else None
        c_uuid = uuid.UUID(str(contact_id)) if contact_id else None
        if cc_uuid and not c_uuid:
            cc_row = db.get(CaseContact, cc_uuid)
            if cc_row and cc_row.contact_id:
                c_uuid = cc_row.contact_id
        recipient = CanarySignRecipient(
            id=uuid.uuid4(),
            signing_request_id=req.id,
            case_contact_id=cc_uuid,
            contact_id=c_uuid,
            name=name,
            email=email,
            routing_order=routing_order,
            sign_token=secrets.token_urlsafe(24),
            status=CanarySignRecipientStatus.pending,
            created_at=now,
        )
        db.add(recipient)
        recipients.append(recipient)
    db.flush()

    for field in _parse_field_specs(db, request_id=req.id, recipients=recipients, fields_specs=fields_specs):
        db.add(field)
    db.flush()

    if supersedes_id:
        old = db.get(CanarySignRequest, supersedes_id)
        if old and old.status == CanarySignStatus.pending:
            old.status = CanarySignStatus.voided
            old.voided_at = now
            old.status_detail = "Superseded by amended request"
            old.updated_at = now
            db.add(old)
            _add_audit(
                db,
                req=old,
                event_type=CanarySignAuditEventType.voided,
                detail={"reason": "Superseded", "superseded_by": str(req.id)},
            )

    _add_audit(db, req=req, event_type=CanarySignAuditEventType.created, detail={"subject": req.subject})
    _add_audit(db, req=req, event_type=CanarySignAuditEventType.sent, detail={"recipient_count": len(recipients)})

    access_codes: dict[uuid.UUID, str] = {}
    for recipient in recipients:
        if recipient.contact_id is None:
            continue
        _row, newly, code = ensure_contact_portal_access_for_delivery(
            db,
            contact_id=recipient.contact_id,
            actor_user_id=actor.id,
        )
        if newly and code:
            access_codes[recipient.id] = code

    try:
        _notify_recipients(
            db,
            req,
            recipients,
            kind=AlertKind.canary_sign_requested,
            access_codes=access_codes,
        )
        _notify_staff_sent(db, case_id, req, actor)
    except Exception as e:
        log.warning("Canary Sign alert e-mail failed after send %s: %s", req.id, e)

    log_event(
        db,
        actor_user_id=actor.id,
        action="canary_sign.request.sent",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(case_id), "source_file_id": str(source_file_id)},
    )
    log_portal_activity(
        db,
        case_id=case_id,
        contact_id=recipients[0].contact_id if recipients else None,
        action="canary_sign.sent",
        summary=f"Canary Sign sent: {req.subject}",
    )
    db.commit()
    db.refresh(req)
    return req


def _notify_recipients(
    db: Session,
    req: CanarySignRequest,
    recipients: list[CanarySignRecipient],
    *,
    kind: AlertKind,
    access_codes: dict[uuid.UUID, str] | None = None,
) -> None:
    if not firm_alerts_configured(db):
        return
    case = db.get(Case, req.case_id)
    matter = client_matter_description(case) if case else "your matter"
    codes = access_codes or {}
    for r in recipients:
        if r.status in (CanarySignRecipientStatus.signed, CanarySignRecipientStatus.declined):
            continue
        ctx: dict[str, Any] = {
            "recipient_name": r.name,
            "document_name": req.subject,
            "matter_label": matter,
            "sign_url": _sign_link(r.sign_token),
        }
        code = codes.get(r.id)
        if code:
            ctx["access_code"] = code
        dispatch_alert(
            db,
            kind,
            to_email=r.email,
            context=ctx,
            actor_user_id=req.sent_by_user_id,
        )


def _notify_staff_sent(db: Session, case_id: uuid.UUID, req: CanarySignRequest, actor: User) -> None:
    if not firm_alerts_configured(db):
        return
    for user in list_portal_staff_recipient_users(db, case_id):
        if not user.email:
            continue
        dispatch_alert(
            db,
            AlertKind.canary_sign_sent_staff,
            to_email=user.email.strip(),
            context={
                "staff_name": user.display_name or user.email,
                "document_name": req.subject,
                "sender_name": actor.display_name or actor.email,
            },
            actor_user_id=actor.id,
        )


def void_signing_request(
    db: Session,
    *,
    req: CanarySignRequest,
    actor: User,
    reason: str,
) -> CanarySignRequest:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be voided")
    req.status = CanarySignStatus.voided
    req.voided_at = utcnow()
    req.status_detail = (reason or "Voided")[:500]
    req.updated_at = utcnow()
    db.add(req)
    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.voided,
        detail={"reason": req.status_detail},
    )
    log_event(
        db,
        actor_user_id=actor.id,
        action="canary_sign.request.voided",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "reason": req.status_detail},
    )
    log_portal_activity(
        db,
        case_id=req.case_id,
        action="canary_sign.voided",
        summary=f"Canary Sign voided: {req.subject}",
    )
    db.commit()
    db.refresh(req)
    return req


def remind_signing_request(db: Session, *, req: CanarySignRequest, actor: User) -> None:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending requests can be reminded")
    all_recipients = _recipients_for_request(db, req.id)
    recipients = [
        r
        for r in all_recipients
        if r.status in (CanarySignRecipientStatus.pending, CanarySignRecipientStatus.viewed)
    ]
    if req.order_mode == CanarySignOrderMode.sequential:
        eligible_order = _next_sequential_order(all_recipients)
        recipients = [r for r in recipients if r.routing_order == eligible_order]
    _notify_recipients(db, req, recipients, kind=AlertKind.canary_sign_reminded)
    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.reminded,
        detail={"recipient_ids": [str(r.id) for r in recipients]},
    )
    log_event(
        db,
        actor_user_id=actor.id,
        action="canary_sign.request.reminded",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id)},
    )
    db.commit()


def _next_sequential_order(recipients: list[CanarySignRecipient]) -> int:
    unsigned = [r for r in recipients if r.status != CanarySignRecipientStatus.signed]
    if not unsigned:
        return 999
    return min(r.routing_order for r in unsigned)


def get_recipient_by_sign_token(db: Session, sign_token: str) -> CanarySignRecipient | None:
    token = (sign_token or "").strip()
    if not token:
        return None
    return db.execute(
        select(CanarySignRecipient).where(CanarySignRecipient.sign_token == token).limit(1)
    ).scalar_one_or_none()


def list_pending_for_contact(
    db: Session, contact_id: uuid.UUID
) -> list[tuple[CanarySignRequest, CanarySignRecipient]]:
    rows = db.execute(
        select(CanarySignRequest, CanarySignRecipient)
        .join(CanarySignRecipient, CanarySignRecipient.signing_request_id == CanarySignRequest.id)
        .where(
            CanarySignRecipient.contact_id == contact_id,
            CanarySignRequest.status == CanarySignStatus.pending,
            CanarySignRecipient.status.in_(
                (CanarySignRecipientStatus.pending, CanarySignRecipientStatus.viewed)
            ),
        )
        .order_by(CanarySignRequest.created_at.desc())
    ).all()
    out: list[tuple[CanarySignRequest, CanarySignRecipient]] = []
    seen: set[uuid.UUID] = set()
    for req, recip in rows:
        mark_expired_if_needed(db, req)
        if req.status != CanarySignStatus.pending:
            continue
        if req.id in seen:
            continue
        seen.add(req.id)
        out.append((req, recip))
    return out


def list_for_contact(
    db: Session, contact_id: uuid.UUID
) -> list[tuple[CanarySignRequest, CanarySignRecipient]]:
    rows = db.execute(
        select(CanarySignRequest, CanarySignRecipient)
        .join(CanarySignRecipient, CanarySignRecipient.signing_request_id == CanarySignRequest.id)
        .where(CanarySignRecipient.contact_id == contact_id)
        .order_by(CanarySignRequest.created_at.desc())
    ).all()
    out: list[tuple[CanarySignRequest, CanarySignRecipient]] = []
    seen: set[uuid.UUID] = set()
    for req, recip in rows:
        mark_expired_if_needed(db, req)
        if req.id in seen:
            continue
        seen.add(req.id)
        out.append((req, recip))
    return out


def _recipient_can_sign_now(db: Session, req: CanarySignRequest, recipient: CanarySignRecipient) -> bool:
    if req.status != CanarySignStatus.pending:
        return False
    if recipient.status in (CanarySignRecipientStatus.signed, CanarySignRecipientStatus.declined):
        return False
    if not _form_gate_allows(req, recipient):
        return False
    if req.order_mode != CanarySignOrderMode.sequential:
        return True
    others = _recipients_for_request(db, req.id)
    for r in others:
        if r.routing_order < recipient.routing_order and r.status != CanarySignRecipientStatus.signed:
            return False
    return True


def _form_gate_allows(req: CanarySignRequest, recipient: CanarySignRecipient) -> bool:
    """Fillable PDFs: until the form filler completes, only they (or anyone if unlocked) may proceed."""
    if not getattr(req, "has_fillable_form", False):
        return True
    if getattr(req, "form_completed_at", None) is not None:
        return True
    locker = getattr(req, "form_locked_by_recipient_id", None)
    if locker is None:
        return True
    return locker == recipient.id


def _snapshot_pdf_bytes(db: Session, req: CanarySignRequest) -> bytes:
    if not req.snapshot_pdf_file_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing snapshot missing")
    row = db.get(DbFile, req.snapshot_pdf_file_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing snapshot missing")
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing snapshot missing on disk")
    return abs_path.read_bytes()


def list_form_fields_for_request(db: Session, req: CanarySignRequest) -> list[dict[str, Any]]:
    if not getattr(req, "has_fillable_form", False):
        return []
    try:
        return extract_acroform_fields(_snapshot_pdf_bytes(db, req))
    except Exception:
        log.exception("AcroForm extract failed for %s", req.id)
        return []


def claim_form_lock(
    db: Session,
    req: CanarySignRequest,
    recipient: CanarySignRecipient,
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> CanarySignRequest:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This signing request is no longer active")
    if not req.has_fillable_form:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This document has no fillable form fields")
    if req.form_completed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The form has already been completed")
    if recipient.status in (CanarySignRecipientStatus.signed, CanarySignRecipientStatus.declined):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot lock the form")
    if req.form_locked_by_recipient_id and req.form_locked_by_recipient_id != recipient.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another recipient has already locked this form for editing",
        )
    if req.form_locked_by_recipient_id == recipient.id:
        return req

    # Respect sequential signing order when claiming the shared form
    if req.order_mode == CanarySignOrderMode.sequential:
        others = _recipients_for_request(db, req.id)
        for r in others:
            if r.routing_order < recipient.routing_order and r.status != CanarySignRecipientStatus.signed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="It is not your turn to act on this request yet",
                )

    now = utcnow()
    req.form_locked_by_recipient_id = recipient.id
    req.form_locked_at = now
    req.updated_at = now
    db.add(req)
    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.form_locked,
        recipient_id=recipient.id,
        detail={"name": recipient.name},
        ip=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(req)
    return req


def save_form_responses(
    db: Session,
    req: CanarySignRequest,
    recipient: CanarySignRecipient,
    responses: dict[str, Any],
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> CanarySignRequest:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This signing request is no longer active")
    if not req.has_fillable_form:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This document has no fillable form fields")
    if req.form_locked_by_recipient_id != recipient.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not hold the form lock")
    if req.form_completed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The form has already been completed")
    if not isinstance(responses, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="responses must be an object")

    known = {f["name"] for f in list_form_fields_for_request(db, req)}
    cleaned: dict[str, Any] = {}
    for key, value in responses.items():
        name = str(key).strip()
        if not name or (known and name not in known):
            continue
        if isinstance(value, bool) or value is None:
            cleaned[name] = value
        else:
            cleaned[name] = str(value)

    req.form_responses = cleaned
    req.updated_at = utcnow()
    db.add(req)
    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.form_filled,
        recipient_id=recipient.id,
        detail={"field_count": len(cleaned)},
        ip=ip,
        user_agent=ua,
    )
    db.commit()
    db.refresh(req)
    return req


def portal_signing_view(
    db: Session,
    req: CanarySignRequest,
    *,
    contact_id: uuid.UUID | None = None,
    recipient: CanarySignRecipient | None = None,
) -> dict[str, Any]:
    mark_expired_if_needed(db, req)
    recipients = _recipients_for_request(db, req.id)
    mine = recipient
    if mine is None and contact_id is not None:
        mine = next((r for r in recipients if r.contact_id == contact_id), None)
    if mine is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a recipient on this signing request")
    fields = [f for f in _fields_for_request(db, req.id) if f.recipient_id == mine.id]
    case = db.get(Case, req.case_id)
    form_fields = list_form_fields_for_request(db, req) if req.has_fillable_form else []
    locker_id = req.form_locked_by_recipient_id
    locker = next((r for r in recipients if r.id == locker_id), None) if locker_id else None
    i_hold_lock = bool(locker_id and locker_id == mine.id)
    form_completed = req.form_completed_at is not None
    can_edit_form = bool(
        req.has_fillable_form
        and req.status == CanarySignStatus.pending
        and not form_completed
        and (locker_id is None or i_hold_lock)
        and mine.status not in (CanarySignRecipientStatus.signed, CanarySignRecipientStatus.declined)
    )
    return {
        "id": str(req.id),
        "subject": req.subject,
        "status": req.status.value,
        "status_detail": req.status_detail,
        "order_mode": req.order_mode.value,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "can_sign": _recipient_can_sign_now(db, req, mine),
        "recipient_id": str(mine.id),
        "recipient_name": mine.name,
        "recipient_status": mine.status.value,
        "sign_token": mine.sign_token,
        "matter_label": client_matter_description(case) if case else "",
        "case_id": str(req.case_id),
        "fields": [_field_out(f) for f in fields],
        "disclaimer": (
            "By signing you agree that this electronic signature is intended as your signature "
            "for this document under the law of England and Wales."
        ),
        "has_fillable_form": bool(req.has_fillable_form),
        "form_fields": form_fields,
        "form_responses": req.form_responses or {},
        "form_locked": locker_id is not None,
        "form_locked_by_recipient_id": str(locker_id) if locker_id else None,
        "form_locked_by_name": locker.name if locker else None,
        "form_lock_held_by_me": i_hold_lock,
        "form_completed": form_completed,
        "can_edit_form": can_edit_form,
        "can_claim_form_lock": bool(
            req.has_fillable_form
            and not form_completed
            and locker_id is None
            and mine.status not in (CanarySignRecipientStatus.signed, CanarySignRecipientStatus.declined)
            and _form_gate_allows(req, mine)
        ),
    }


def record_view(
    db: Session,
    req: CanarySignRequest,
    recipient: CanarySignRecipient,
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> None:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        return
    if recipient.status == CanarySignRecipientStatus.pending:
        recipient.status = CanarySignRecipientStatus.viewed
        recipient.viewed_at = utcnow()
        db.add(recipient)
        _add_audit(
            db,
            req=req,
            event_type=CanarySignAuditEventType.viewed,
            recipient_id=recipient.id,
            ip=ip,
            user_agent=ua,
        )
        db.commit()


def _validate_field_value(field: CanarySignField, value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Field value must be an object")
    ft = field.field_type
    if ft in (CanarySignFieldType.signature, CanarySignFieldType.initials):
        has_img = bool(value.get("image_b64") or value.get("png_b64"))
        has_text = bool(str(value.get("text") or "").strip())
        if field.required and not has_img and not has_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing {ft.value}")
    elif ft == CanarySignFieldType.checkbox:
        if field.required and "checked" not in value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing checkbox value")
    else:
        if field.required and not str(value.get("text") or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing {ft.value}")
    return value


def submit_signature(
    db: Session,
    req: CanarySignRequest,
    recipient: CanarySignRecipient,
    *,
    field_values: dict[str, Any],
    ip: str | None = None,
    ua: str | None = None,
    consent: bool = True,
    form_responses: dict[str, Any] | None = None,
) -> CanarySignRequest:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This signing request is no longer active")
    if not consent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required to sign")
    if not _recipient_can_sign_now(db, req, recipient):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="It is not your turn to sign yet" if req.order_mode == CanarySignOrderMode.sequential else "Cannot sign",
        )

    now = utcnow()

    # Fillable PDF gate: locker must supply/save form answers and mark form complete on their sign
    if req.has_fillable_form:
        if req.form_completed_at is None:
            if req.form_locked_by_recipient_id != recipient.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The fillable form must be completed by the recipient who locked it before others can sign",
                )
            merged = dict(req.form_responses or {})
            if isinstance(form_responses, dict):
                for key, value in form_responses.items():
                    name = str(key).strip()
                    if not name:
                        continue
                    merged[name] = value if isinstance(value, bool) or value is None else str(value)
            req.form_responses = merged
            req.form_completed_at = now
            req.updated_at = now
            db.add(req)
            _add_audit(
                db,
                req=req,
                event_type=CanarySignAuditEventType.form_filled,
                recipient_id=recipient.id,
                detail={"field_count": len(merged), "completed": True},
                ip=ip,
                user_agent=ua,
            )

    fields = [f for f in _fields_for_request(db, req.id) if f.recipient_id == recipient.id]
    by_id = {str(f.id): f for f in fields}

    for field in fields:
        raw = field_values.get(str(field.id))
        if raw is None and field.required:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing value for field {field.label or field.field_type.value}")
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid field value")
        value = _validate_field_value(field, raw)
        if field.page is None or field.x_pct is None or field.y_pct is None or field.w_pct is None or field.h_pct is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field {field.label or field.field_type.value} has no placement; ask the sender to amend and re-send",
            )
        stored = {k: v for k, v in value.items() if k not in ("page", "x_pct", "y_pct", "w_pct", "h_pct")}
        field.value = stored
        field.filled_at = now
        db.add(field)

    for key in field_values:
        if str(key) not in by_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown field {key}")

    recipient.status = CanarySignRecipientStatus.signed
    recipient.signed_at = now
    recipient.signed_ip = (ip or "")[:64] or None
    recipient.signed_user_agent = (ua or "")[:500] or None
    if recipient.viewed_at is None:
        recipient.viewed_at = now
    db.add(recipient)
    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.signed,
        recipient_id=recipient.id,
        detail={"name": recipient.name},
        ip=ip,
        user_agent=ua,
    )

    all_recipients = _recipients_for_request(db, req.id)
    for i, r in enumerate(all_recipients):
        if r.id == recipient.id:
            all_recipients[i] = recipient
    if all(r.status == CanarySignRecipientStatus.signed for r in all_recipients):
        complete_signing_request(db, req)
    else:
        req.updated_at = now
        db.add(req)
        db.commit()
        db.refresh(req)
    return req


def decline_signing(
    db: Session,
    req: CanarySignRequest,
    recipient: CanarySignRecipient,
    *,
    reason: str,
    ip: str | None = None,
    ua: str | None = None,
) -> CanarySignRequest:
    mark_expired_if_needed(db, req)
    if req.status != CanarySignStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This signing request is no longer active")
    if recipient.status == CanarySignRecipientStatus.signed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already signed")

    now = utcnow()
    reason_text = (reason or "").strip()[:2000] or "Declined"
    recipient.status = CanarySignRecipientStatus.declined
    recipient.decline_reason = reason_text
    db.add(recipient)

    req.status = CanarySignStatus.declined
    req.status_detail = f"Declined by {recipient.name}: {reason_text}"[:500]
    req.updated_at = now
    db.add(req)

    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.declined,
        recipient_id=recipient.id,
        detail={"reason": reason_text},
        ip=ip,
        user_agent=ua,
    )
    log_portal_activity(
        db,
        case_id=req.case_id,
        contact_id=recipient.contact_id,
        action="canary_sign.declined",
        summary=f"Canary Sign declined: {req.subject}",
    )
    _notify_staff_declined(db, req, recipient, reason_text)
    log_event(
        db,
        actor_user_id=None,
        action="canary_sign.request.declined",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "recipient_id": str(recipient.id)},
    )
    db.commit()
    db.refresh(req)
    return req


def _notify_staff_declined(db: Session, req: CanarySignRequest, recipient: CanarySignRecipient, reason: str) -> None:
    if not firm_alerts_configured(db):
        return
    for user in list_portal_staff_recipient_users(db, req.case_id):
        if not user.email:
            continue
        dispatch_alert(
            db,
            AlertKind.canary_sign_declined_staff,
            to_email=user.email.strip(),
            context={
                "staff_name": user.display_name or user.email,
                "document_name": req.subject,
                "recipient_name": recipient.name,
                "decline_reason": reason,
            },
            actor_user_id=req.sent_by_user_id,
        )


def complete_signing_request(db: Session, req: CanarySignRequest, *, detail: str | None = None) -> None:
    if req.status == CanarySignStatus.completed:
        return

    snapshot = db.get(DbFile, req.snapshot_pdf_file_id) if req.snapshot_pdf_file_id else None
    source = db.get(DbFile, req.source_file_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing snapshot missing")

    ensure_files_root()
    abs_path = (FILES_ROOT / snapshot.storage_path).resolve()
    if not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing snapshot missing on disk")
    pdf_bytes = abs_path.read_bytes()

    # Apply fillable form answers and flatten before stamping Canary Sign overlays
    if getattr(req, "has_fillable_form", False) and req.form_responses:
        try:
            pdf_bytes = fill_and_flatten_acroform(pdf_bytes, req.form_responses)
        except Exception as e:
            log.exception("Canary Sign form fill/flatten failed for %s", req.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e).strip() or "Failed to fill form fields in PDF",
            ) from e

    fields = _fields_for_request(db, req.id)
    stamps = []
    for f in fields:
        if not f.value or f.page is None or f.x_pct is None or f.y_pct is None or f.w_pct is None or f.h_pct is None:
            continue
        stamp = stamp_from_field_value(
            page=int(f.page),
            x_pct=float(f.x_pct),
            y_pct=float(f.y_pct),
            w_pct=float(f.w_pct),
            h_pct=float(f.h_pct),
            field_type=f.field_type.value,
            value=f.value,
        )
        if stamp:
            stamps.append(stamp)

    try:
        signed_bytes = stamp_signed_pdf(pdf_bytes, stamps)
    except Exception as e:
        log.exception("Canary Sign stamp failed for %s", req.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e).strip() or "Failed to stamp signed PDF",
        ) from e

    folder_path = (source.folder_path if source else "") or ""
    owner_id = req.sent_by_user_id or (source.owner_id if source else None)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No owner for signed file")

    stem = Path(source.original_filename if source else req.subject).stem or "document"
    signed = _save_case_file(
        db,
        case_id=req.case_id,
        owner_id=owner_id,
        folder_path=folder_path,
        filename=f"{stem} (signed).pdf",
        mime_type="application/pdf",
        raw=signed_bytes,
        category=FileCategory.case_document,
        parent_file_id=source.id if source else None,
    )

    recipients = _recipients_for_request(db, req.id)
    case = db.get(Case, req.case_id)
    matter = client_matter_description(case) if case else ""
    cert_bytes = build_audit_certificate_pdf(
        subject=req.subject,
        matter_label=matter,
        signers=[
            {
                "name": r.name,
                "email": r.email,
                "signed_at": r.signed_at.isoformat() if r.signed_at else None,
                "ip": r.signed_ip,
                "user_agent": r.signed_user_agent,
            }
            for r in recipients
        ],
        completed_at=utcnow(),
        request_id=str(req.id),
    )
    cert_file = _save_case_file(
        db,
        case_id=req.case_id,
        owner_id=owner_id,
        folder_path=folder_path,
        filename=f"{stem} (Canary Sign certificate).pdf",
        mime_type="application/pdf",
        raw=cert_bytes,
        category=FileCategory.case_document,
        parent_file_id=source.id if source else None,
    )

    now = utcnow()
    req.status = CanarySignStatus.completed
    req.signed_file_id = signed.id
    req.certificate_file_id = cert_file.id
    req.completed_at = now
    req.updated_at = now
    req.status_detail = detail
    db.add(req)

    _add_audit(
        db,
        req=req,
        event_type=CanarySignAuditEventType.completed,
        detail={"signed_file_id": str(signed.id), "certificate_file_id": str(cert_file.id)},
    )

    # Case note for fee earner visibility
    if req.sent_by_user_id:
        names = ", ".join(r.name for r in recipients)
        db.add(
            CaseNote(
                id=uuid.uuid4(),
                case_id=req.case_id,
                author_user_id=req.sent_by_user_id,
                body=f"Canary Sign completed: {req.subject}\nSigned by: {names}\nFiled as: {signed.original_filename}",
                created_at=now,
                updated_at=now,
            )
        )

    log_portal_activity(
        db,
        case_id=req.case_id,
        action="canary_sign.completed",
        summary=f"Canary Sign completed: {req.subject}",
    )
    log_event(
        db,
        actor_user_id=req.sent_by_user_id,
        action="canary_sign.request.completed",
        entity_type="canary_sign_request",
        entity_id=str(req.id),
        meta={"case_id": str(req.case_id), "signed_file_id": str(signed.id)},
    )
    _notify_staff_completed(db, req)
    db.commit()


def _notify_staff_completed(db: Session, req: CanarySignRequest) -> None:
    if not firm_alerts_configured(db):
        return
    for user in list_portal_staff_recipient_users(db, req.case_id):
        if not user.email:
            continue
        dispatch_alert(
            db,
            AlertKind.canary_sign_completed_staff,
            to_email=user.email.strip(),
            context={
                "staff_name": user.display_name or user.email,
                "document_name": req.subject,
            },
            actor_user_id=req.sent_by_user_id,
        )


def _recipients_summary(recipients: list[CanarySignRecipient]) -> str:
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
    status_filter: CanarySignStatus | None = None,
) -> list[dict[str, Any]]:
    q = (
        select(CanarySignRequest, Case)
        .join(Case, CanarySignRequest.case_id == Case.id)
        .order_by(CanarySignRequest.created_at.desc())
    )
    if status_filter is not None:
        q = q.where(CanarySignRequest.status == status_filter)
    rows = db.execute(q).all()
    if not rows:
        return []

    req_ids = [req.id for req, _ in rows]
    recipients = db.execute(
        select(CanarySignRecipient).where(CanarySignRecipient.signing_request_id.in_(req_ids))
    ).scalars().all()
    recip_by_req: dict[uuid.UUID, list[CanarySignRecipient]] = {}
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
        mark_expired_if_needed(db, req)
        if status_filter is not None and req.status != status_filter:
            continue
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
                "subject": req.subject,
                "source_filename": file_map.get(req.source_file_id, "") if req.source_file_id else "",
                "status": req.status.value,
                "status_detail": req.status_detail,
                "order_mode": req.order_mode.value,
                "sent_by_display_name": sender_map.get(req.sent_by_user_id) if req.sent_by_user_id else None,
                "recipients_summary": _recipients_summary(recips),
                "expires_at": req.expires_at,
                "created_at": req.created_at,
                "completed_at": req.completed_at,
                "voided_at": req.voided_at,
            }
        )
    return out


def list_case_requests(db: Session, case_id: uuid.UUID) -> list[CanarySignRequest]:
    rows = list(
        db.execute(
            select(CanarySignRequest)
            .where(CanarySignRequest.case_id == case_id)
            .order_by(CanarySignRequest.created_at.desc())
        )
        .scalars()
        .all()
    )
    for req in rows:
        mark_expired_if_needed(db, req)
    return rows


def read_snapshot_pdf_bytes(db: Session, req: CanarySignRequest) -> bytes:
    if not req.snapshot_pdf_file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot PDF not available")
    row = db.get(DbFile, req.snapshot_pdf_file_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot PDF not available")
    ensure_files_root()
    abs_path = (FILES_ROOT / row.storage_path).resolve()
    if not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot PDF missing on disk")
    return abs_path.read_bytes()
