"""Send quotes via portal and record client accept/decline responses."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert, firm_alerts_configured, portal_public_url
from app.audit import log_event
from app.models import (
    Case,
    CaseContact,
    Contact,
    ContactPortalAccess,
    ContactPortalGrant,
    File,
    QuotePortalDelivery,
    QuotePortalDeliveryStatus,
    User,
)
from app.portal_activity import log_portal_activity
from app.portal_case import require_case_portal_enabled
from app.portal_notifications import ALERTS_NOT_CONFIGURED_MSG, list_portal_staff_recipient_users
from app.portal_service import (
    contact_display_name,
    file_folder_in_grant,
    grant_is_active,
    portal_access_is_active,
)
from app.security import create_portal_quote_exchange_token


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _quote_link(exchange_token: str) -> str:
    base = portal_public_url().rstrip("/")
    return f"{base}?quote={exchange_token}"


def supersede_pending_quote_deliveries(db: Session, file_id: uuid.UUID) -> int:
    """Mark pending deliveries superseded when the quote file version changes."""
    now = utcnow()
    rows = (
        db.execute(
            select(QuotePortalDelivery).where(
                QuotePortalDelivery.file_id == file_id,
                QuotePortalDelivery.status == QuotePortalDeliveryStatus.pending,
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = QuotePortalDeliveryStatus.superseded
        row.responded_at = now
    if rows:
        db.flush()
    return len(rows)


def latest_delivery_for_file(db: Session, file_id: uuid.UUID) -> QuotePortalDelivery | None:
    return (
        db.execute(
            select(QuotePortalDelivery)
            .where(QuotePortalDelivery.file_id == file_id)
            .order_by(QuotePortalDelivery.sent_at.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )


def delivery_out_meta(db: Session, delivery: QuotePortalDelivery) -> dict:
    contact = db.get(Contact, delivery.contact_id)
    return {
        "id": str(delivery.id),
        "file_id": str(delivery.file_id),
        "contact_id": str(delivery.contact_id),
        "contact_name": contact_display_name(contact) if contact else "Contact",
        "status": delivery.status.value,
        "sent_at": delivery.sent_at.isoformat(),
        "responded_at": delivery.responded_at.isoformat() if delivery.responded_at else None,
        "decline_reason": delivery.decline_reason,
        "file_version_at_send": delivery.file_version_at_send,
    }


def _grant_covering_file(
    db: Session,
    *,
    case_id: uuid.UUID,
    contact_id: uuid.UUID,
    folder_path: str,
) -> ContactPortalGrant | None:
    grants = (
        db.execute(
            select(ContactPortalGrant).where(
                ContactPortalGrant.case_id == case_id,
                ContactPortalGrant.contact_id == contact_id,
            )
        )
        .scalars()
        .all()
    )
    for grant in grants:
        if grant_is_active(grant) and file_folder_in_grant(
            file_folder=folder_path,
            grant_folder=grant.folder_path or "",
        ):
            return grant
    return None


def pick_portal_grant_for_case(
    db: Session,
    *,
    case_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> ContactPortalGrant | None:
    """Any active portal share on the matter (prefer download-capable grants)."""
    grants = [
        g
        for g in db.execute(
            select(ContactPortalGrant).where(
                ContactPortalGrant.case_id == case_id,
                ContactPortalGrant.contact_id == contact_id,
            )
        )
        .scalars()
        .all()
        if grant_is_active(g)
    ]
    if not grants:
        return None
    downloadable = [g for g in grants if g.can_download]
    return downloadable[0] if downloadable else grants[0]


def quote_delivery_grants_file_access(
    db: Session,
    *,
    contact_id: uuid.UUID,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
) -> QuotePortalDelivery | None:
    """Delivery-scoped file access (pending, accepted, or declined — not superseded)."""
    return (
        db.execute(
            select(QuotePortalDelivery)
            .where(
                QuotePortalDelivery.contact_id == contact_id,
                QuotePortalDelivery.case_id == case_id,
                QuotePortalDelivery.file_id == file_id,
                QuotePortalDelivery.status.in_(
                    (
                        QuotePortalDeliveryStatus.pending,
                        QuotePortalDeliveryStatus.accepted,
                        QuotePortalDeliveryStatus.declined,
                    )
                ),
            )
            .order_by(QuotePortalDelivery.sent_at.desc())
            .limit(1)
        )
        .scalar_one_or_none()
    )


def send_quote_via_portal(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    contact_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> tuple[QuotePortalDelivery, bool, str | None]:
    """Create delivery, e-mail contact, return (delivery, email_sent, skip_reason)."""
    if not firm_alerts_configured(db):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ALERTS_NOT_CONFIGURED_MSG)

    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    require_case_portal_enabled(db, case_id)

    row = db.get(File, file_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.oo_compose_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save and close the quote in the editor before sending via portal.",
        )

    on_case = db.execute(
        select(CaseContact).where(CaseContact.case_id == case_id, CaseContact.contact_id == contact_id)
    ).scalar_one_or_none()
    if on_case is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact is not on this matter")

    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    email = (contact.email or "").strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact has no e-mail address")

    access = db.execute(
        select(ContactPortalAccess).where(ContactPortalAccess.contact_id == contact_id)
    ).scalar_one_or_none()
    if access is None or not portal_access_is_active(access):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Portal access is not active for this contact")

    # Quotes are delivery-scoped — folder grants are optional (used for portal navigation when present).
    grant = _grant_covering_file(
        db,
        case_id=case_id,
        contact_id=contact_id,
        folder_path=row.folder_path or "",
    ) or pick_portal_grant_for_case(db, case_id=case_id, contact_id=contact_id)

    supersede_pending_quote_deliveries(db, file_id)

    if not row.is_portal_quote:
        row.is_portal_quote = True
        row.updated_at = utcnow()
        db.add(row)

    now = utcnow()
    delivery = QuotePortalDelivery(
        id=uuid.uuid4(),
        case_id=case_id,
        file_id=file_id,
        contact_id=contact_id,
        grant_id=grant.id if grant else None,
        sent_by_user_id=actor_user_id,
        file_version_at_send=int(row.version or 1),
        status=QuotePortalDeliveryStatus.pending,
        sent_at=now,
    )
    db.add(delivery)
    db.flush()

    exchange = create_portal_quote_exchange_token(
        contact_id=str(contact_id),
        case_id=str(case_id),
        file_id=str(file_id),
        delivery_id=str(delivery.id),
    )
    quote_url = _quote_link(exchange)
    log_portal_activity(
        db,
        case_id=case_id,
        contact_id=contact_id,
        grant_id=grant.id if grant else None,
        action="portal.quote.sent",
        summary=f"Quote sent to {contact_display_name(contact)} via portal ({row.original_filename})",
    )

    email_sent = dispatch_alert(
        db,
        AlertKind.portal_quote_sent,
        to_email=email,
        context={
            "contact_name": contact_display_name(contact),
            "quote_filename": row.original_filename,
            "portal_url": quote_url,
        },
        actor_user_id=actor_user_id,
    )
    skip_reason = None if email_sent else ALERTS_NOT_CONFIGURED_MSG

    log_event(
        db,
        actor_user_id=actor_user_id,
        action="quote.portal.send",
        entity_type="quote_portal_delivery",
        entity_id=str(delivery.id),
        meta={
            "case_id": str(case_id),
            "file_id": str(file_id),
            "contact_id": str(contact_id),
            "file_version": delivery.file_version_at_send,
            "email_sent": email_sent,
        },
    )
    db.refresh(delivery)
    return delivery, email_sent, skip_reason


def _notify_staff_quote_response(
    db: Session,
    *,
    case_id: uuid.UUID,
    contact: Contact,
    filename: str,
    accepted: bool,
    decline_reason: str | None,
) -> None:
    if not firm_alerts_configured(db):
        return
    kind = AlertKind.portal_quote_accepted if accepted else AlertKind.portal_quote_declined
    for user in list_portal_staff_recipient_users(db, case_id):
        addr = (user.email or "").strip()
        if not addr:
            continue
        dispatch_alert(
            db,
            kind,
            to_email=addr,
            context={
                "contact_name": contact_display_name(contact),
                "quote_filename": filename,
                "decline_reason": (decline_reason or "").strip(),
            },
        )


def respond_to_quote_delivery(
    db: Session,
    *,
    delivery: QuotePortalDelivery,
    contact: Contact,
    accepted: bool,
    decline_reason: str | None,
) -> QuotePortalDelivery:
    if delivery.contact_id != contact.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    if delivery.status != QuotePortalDeliveryStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This quote is no longer awaiting a response")

    row = db.get(File, delivery.file_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote file not found")
    current_version = int(row.version or 1)
    if current_version != int(delivery.file_version_at_send):
        delivery.status = QuotePortalDeliveryStatus.superseded
        delivery.responded_at = utcnow()
        db.add(delivery)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This quote has been revised. Ask your firm for an updated copy.",
        )

    now = utcnow()
    delivery.status = QuotePortalDeliveryStatus.accepted if accepted else QuotePortalDeliveryStatus.declined
    delivery.responded_at = now
    reason = (decline_reason or "").strip() or None
    if not accepted:
        delivery.decline_reason = reason
    db.add(delivery)

    verb = "accepted" if accepted else "declined"
    summary = f"{contact_display_name(contact)} {verb} quote {row.original_filename}"
    if not accepted and reason:
        summary = f"{summary}: {reason}"
    log_portal_activity(
        db,
        case_id=delivery.case_id,
        contact_id=contact.id,
        grant_id=delivery.grant_id,
        action=f"portal.quote.{verb}",
        summary=summary,
    )
    log_event(
        db,
        actor_user_id=None,
        action=f"quote.portal.{verb}",
        entity_type="quote_portal_delivery",
        entity_id=str(delivery.id),
        meta={
            "case_id": str(delivery.case_id),
            "file_id": str(delivery.file_id),
            "contact_id": str(contact.id),
            "decline_reason": reason,
        },
    )
    _notify_staff_quote_response(
        db,
        case_id=delivery.case_id,
        contact=contact,
        filename=row.original_filename,
        accepted=accepted,
        decline_reason=reason,
    )
    db.commit()
    db.refresh(delivery)
    return delivery


def get_delivery_for_contact(db: Session, delivery_id: uuid.UUID, contact_id: uuid.UUID) -> QuotePortalDelivery:
    delivery = db.get(QuotePortalDelivery, delivery_id)
    if delivery is None or delivery.contact_id != contact_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return delivery


def delivery_can_respond(db: Session, delivery: QuotePortalDelivery) -> bool:
    if delivery.status != QuotePortalDeliveryStatus.pending:
        return False
    row = db.get(File, delivery.file_id)
    if row is None:
        return False
    return int(row.version or 1) == int(delivery.file_version_at_send)


def portal_quote_delivery_view(
    db: Session,
    delivery: QuotePortalDelivery,
    *,
    grant: ContactPortalGrant | None = None,
) -> dict:
    from app.portal_service import relative_folder_under_grant

    row = db.get(File, delivery.file_id)
    filename = row.original_filename if row else "Document"
    folder_display = ""
    if row and grant is not None:
        if file_folder_in_grant(file_folder=row.folder_path or "", grant_folder=grant.folder_path or ""):
            folder_display = (
                relative_folder_under_grant(
                    grant_folder=grant.folder_path or "",
                    absolute_folder=row.folder_path or "",
                )
                or ""
            )
        else:
            folder_display = row.folder_path or ""
    return {
        "id": delivery.id,
        "file_id": delivery.file_id,
        "grant_id": delivery.grant_id,
        "original_filename": filename,
        "mime_type": row.mime_type if row else "application/octet-stream",
        "size_bytes": int(row.size_bytes or 0) if row else 0,
        "folder_display": folder_display,
        "status": delivery.status.value,
        "can_respond": delivery_can_respond(db, delivery),
        "decline_reason": delivery.decline_reason,
        "responded_at": delivery.responded_at,
    }


def list_pending_quote_deliveries_for_contact(
    db: Session,
    *,
    contact_id: uuid.UUID,
) -> list[QuotePortalDelivery]:
    """Pending quotes for this contact across all matters (folder grants not required)."""
    rows = (
        db.execute(
            select(QuotePortalDelivery)
            .where(
                QuotePortalDelivery.contact_id == contact_id,
                QuotePortalDelivery.status == QuotePortalDeliveryStatus.pending,
            )
            .order_by(QuotePortalDelivery.sent_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[QuotePortalDelivery] = []
    for delivery in rows:
        if not delivery_can_respond(db, delivery):
            continue
        if db.get(File, delivery.file_id) is None:
            continue
        out.append(delivery)
    return out


def get_quote_delivery_file_for_contact(
    db: Session,
    *,
    delivery_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> tuple[QuotePortalDelivery, File]:
    """File access for a sent quote (independent of folder grants)."""
    delivery = get_delivery_for_contact(db, delivery_id, contact_id)
    if delivery.status == QuotePortalDeliveryStatus.superseded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This quote has been revised. Ask your firm for an updated copy.",
        )
    row = db.get(File, delivery.file_id)
    if row is None or row.case_id != delivery.case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote file not found")
    if row.oo_compose_pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote file not found")
    return delivery, row


def list_pending_approvals_for_grant(
    db: Session,
    *,
    contact_id: uuid.UUID,
    grant: ContactPortalGrant,
) -> list[QuotePortalDelivery]:
    """Pending quote deliveries for this contact on the matter (any folder)."""
    rows = (
        db.execute(
            select(QuotePortalDelivery)
            .where(
                QuotePortalDelivery.contact_id == contact_id,
                QuotePortalDelivery.case_id == grant.case_id,
                QuotePortalDelivery.status == QuotePortalDeliveryStatus.pending,
            )
            .order_by(QuotePortalDelivery.sent_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[QuotePortalDelivery] = []
    for delivery in rows:
        if not delivery_can_respond(db, delivery):
            continue
        if db.get(File, delivery.file_id) is None:
            continue
        out.append(delivery)
    return out


def set_portal_quote_tag(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    is_portal_quote: bool,
    actor_user_id: uuid.UUID,
) -> File:
    row = db.get(File, file_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row.mime_type == "application/x-directory":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folders cannot be marked as portal quotes")
    if row.is_portal_quote == is_portal_quote:
        return row

    row.is_portal_quote = is_portal_quote
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)

    log_event(
        db,
        actor_user_id=actor_user_id,
        action="quote.portal.tag" if is_portal_quote else "quote.portal.untag",
        entity_type="file",
        entity_id=str(row.id),
        meta={
            "case_id": str(case_id),
            "filename": row.original_filename,
            "folder_path": row.folder_path,
        },
    )
    return row
