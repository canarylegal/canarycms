"""Staff: send quotes via portal and view delivery status."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.alert_dispatch import firm_alerts_configured
from app.db import get_db
from app.deps import get_current_user, require_case_access
from app.models import Contact, File, User
from app.quote_portal_service import (
    delivery_can_respond,
    delivery_out_meta,
    get_delivery_for_contact,
    latest_delivery_for_file,
    respond_to_quote_delivery,
    send_quote_via_portal,
)
from app.schemas import QuotePortalDeliveryOut, QuotePortalSendPreflightOut, SendQuoteViaPortalIn

router = APIRouter(prefix="/cases/{case_id}/files/{file_id}/quote-portal", tags=["quote-portal"])


def _delivery_out(
    db: Session,
    delivery,
    *,
    email_sent: bool = False,
    email_skip_reason: str | None = None,
    portal_pdf_generated: bool | None = None,
) -> QuotePortalDeliveryOut:
    meta = delivery_out_meta(db, delivery)
    return QuotePortalDeliveryOut(
        id=delivery.id,
        file_id=delivery.file_id,
        contact_id=delivery.contact_id,
        contact_name=meta["contact_name"],
        status=delivery.status.value,
        sent_at=delivery.sent_at,
        responded_at=delivery.responded_at,
        decline_reason=delivery.decline_reason,
        file_version_at_send=delivery.file_version_at_send,
        email_sent=email_sent,
        email_skip_reason=email_skip_reason,
        portal_pdf_generated=(
            portal_pdf_generated
            if portal_pdf_generated is not None
            else bool(meta.get("portal_pdf_generated"))
        ),
    )


@router.get("/delivery", response_model=QuotePortalDeliveryOut | None)
def get_quote_portal_delivery(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuotePortalDeliveryOut | None:
    require_case_access(case_id, user, db)
    row = db.get(File, file_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    delivery = latest_delivery_for_file(db, file_id)
    if delivery is None:
        return None
    return _delivery_out(db, delivery)


@router.get("/send-preflight", response_model=QuotePortalSendPreflightOut)
def get_quote_portal_send_preflight(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuotePortalSendPreflightOut:
    require_case_access(case_id, user, db)
    row = db.get(File, file_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return QuotePortalSendPreflightOut(alerts_configured=firm_alerts_configured(db))


@router.post("/send", response_model=QuotePortalDeliveryOut)
def post_send_quote_via_portal(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: SendQuoteViaPortalIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuotePortalDeliveryOut:
    require_case_access(case_id, user, db)
    delivery, email_sent, skip_reason, portal_pdf_generated = send_quote_via_portal(
        db,
        case_id=case_id,
        file_id=file_id,
        contact_id=payload.contact_id,
        actor_user_id=user.id,
    )
    return _delivery_out(
        db,
        delivery,
        email_sent=email_sent,
        email_skip_reason=skip_reason,
        portal_pdf_generated=portal_pdf_generated,
    )
