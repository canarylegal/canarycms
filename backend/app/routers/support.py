"""Staff support tickets and bug reports — e-mailed to Canary."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user
from app.firm_email_service import FirmEmailMessage, send_firm_email
from app.models import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

SUPPORT_INBOX = "colin@canarylegalsoftware.co.uk"

SupportKind = Literal["support", "bug"]


URGENCY_LABELS: dict[int, str] = {
    1: "Slight problem",
    2: "Low",
    3: "Normal",
    4: "High",
    5: "Urgent",
}


class SupportTicketIn(BaseModel):
    kind: SupportKind
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
    urgency: int = Field(ge=1, le=5)
    phone: str | None = Field(default=None, max_length=40)


class SupportTicketOut(BaseModel):
    ok: bool = True


def _kind_label(kind: SupportKind) -> str:
    return "Bug report" if kind == "bug" else "Support ticket"


@router.post("/ticket", response_model=SupportTicketOut)
def submit_support_ticket(
    payload: SupportTicketIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SupportTicketOut:
    subject = (payload.subject or "").strip()
    message = (payload.message or "").strip()
    phone = (payload.phone or "").strip()
    if not subject or not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject and message are required.")

    label = _kind_label(payload.kind)
    display = (user.display_name or "").strip() or user.email
    urgency = int(payload.urgency)
    urgency_label = URGENCY_LABELS.get(urgency, str(urgency))
    mail_subject = f"[Canary {label}] [U{urgency}] {subject}"
    body_text = (
        f"{label}\n"
        f"{'=' * len(label)}\n\n"
        f"From: {display} <{user.email}>\n"
        f"User id: {user.id}\n"
        f"Initials: {user.initials}\n"
        f"Job title: {(user.job_title or '').strip() or '—'}\n"
        f"Phone: {phone or '—'}\n"
        f"Urgency: {urgency}/5 ({urgency_label})\n\n"
        f"Subject: {subject}\n\n"
        f"{message}\n"
    )

    try:
        send_firm_email(
            db,
            FirmEmailMessage(
                to_email=SUPPORT_INBOX,
                subject=mail_subject,
                body_text=body_text,
            ),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except Exception as e:
        log.exception("support ticket send failed user=%s", user.email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not send the ticket e-mail: {e}",
        ) from e

    log_event(
        db,
        actor_user_id=user.id,
        action="support.ticket.submit",
        entity_type="support_ticket",
        entity_id=None,
        meta={
            "kind": payload.kind,
            "subject": subject[:120],
            "urgency": urgency,
            "phone_provided": bool(phone),
        },
    )
    db.commit()
    return SupportTicketOut()
