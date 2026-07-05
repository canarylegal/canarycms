"""E-mail staff when anticipated payments or pending invoices are approved or rejected."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.alert_dispatch import AlertKind, dispatch_alert
from app.models import Case, User


def _user_label(user: User | None) -> str:
    if user is None:
        return "A colleague"
    return (user.display_name or user.email or "A colleague").strip()


def _format_gbp(pence: int) -> str:
    return f"£{pence / 100:.2f}"


def _case_labels(db: Session, case_id: uuid.UUID) -> tuple[str, str]:
    case = db.get(Case, case_id)
    if case is None:
        return "", ""
    return (case.case_number or "").strip(), (case.title or "").strip()


def _notify_user(
    db: Session,
    *,
    recipient_user_id: uuid.UUID | None,
    actor: User,
    kind: AlertKind,
    context: dict[str, str],
) -> None:
    if recipient_user_id is None or recipient_user_id == actor.id:
        return
    recipient = db.get(User, recipient_user_id)
    if recipient is None or not recipient.is_active:
        return
    email = (recipient.email or "").strip()
    if not email:
        return
    dispatch_alert(
        db,
        kind,
        to_email=email,
        context={
            **context,
            "staff_name": _user_label(recipient),
        },
        actor_user_id=actor.id,
    )


def notify_anticipated_payment_approved(
    db: Session,
    *,
    case_id: uuid.UUID,
    poster_user_id: uuid.UUID | None,
    actor: User,
    description: str,
    amount_pence: int,
    reference: str | None,
) -> None:
    case_number, matter_title = _case_labels(db, case_id)
    _notify_user(
        db,
        recipient_user_id=poster_user_id,
        actor=actor,
        kind=AlertKind.anticipated_payment_approved,
        context={
            "decider_name": _user_label(actor),
            "case_number": case_number,
            "matter_label": matter_title or case_number or "your matter",
            "description": (description or "").strip() or "Anticipated payment",
            "amount_gbp": _format_gbp(amount_pence),
            "reference": (reference or "").strip(),
        },
    )


def notify_anticipated_payment_amended(
    db: Session,
    *,
    case_id: uuid.UUID,
    actor: User,
    poster_user_id: uuid.UUID,
    description: str,
    amount_pence: int,
    reference: str | None,
) -> None:
    case = db.get(Case, case_id)
    if case is None or case.fee_earner_user_id is None:
        return
    if actor.id == case.fee_earner_user_id:
        return
    case_number, matter_title = _case_labels(db, case_id)
    poster = db.get(User, poster_user_id)
    _notify_user(
        db,
        recipient_user_id=case.fee_earner_user_id,
        actor=actor,
        kind=AlertKind.anticipated_payment_amended,
        context={
            "editor_name": _user_label(actor),
            "poster_name": _user_label(poster),
            "case_number": case_number,
            "matter_label": matter_title or case_number or "your matter",
            "description": (description or "").strip() or "Anticipated payment",
            "amount_gbp": _format_gbp(amount_pence),
            "reference": (reference or "").strip(),
        },
    )


def notify_anticipated_payment_rejected(
    db: Session,
    *,
    case_id: uuid.UUID,
    poster_user_id: uuid.UUID | None,
    actor: User,
    description: str,
    amount_pence: int,
    reference: str | None,
    comment: str | None,
) -> None:
    case_number, matter_title = _case_labels(db, case_id)
    _notify_user(
        db,
        recipient_user_id=poster_user_id,
        actor=actor,
        kind=AlertKind.anticipated_payment_rejected,
        context={
            "decider_name": _user_label(actor),
            "case_number": case_number,
            "matter_label": matter_title or case_number or "your matter",
            "description": (description or "").strip() or "Anticipated payment",
            "amount_gbp": _format_gbp(amount_pence),
            "reference": (reference or "").strip(),
            "comment": (comment or "").strip(),
        },
    )


def notify_invoice_approved(
    db: Session,
    *,
    case_id: uuid.UUID,
    creator_user_id: uuid.UUID | None,
    actor: User,
    invoice_number: str,
    total_pence: int,
) -> None:
    case_number, matter_title = _case_labels(db, case_id)
    _notify_user(
        db,
        recipient_user_id=creator_user_id,
        actor=actor,
        kind=AlertKind.invoice_approved,
        context={
            "decider_name": _user_label(actor),
            "case_number": case_number,
            "matter_label": matter_title or case_number or "your matter",
            "invoice_number": invoice_number,
            "amount_gbp": _format_gbp(total_pence),
        },
    )


def notify_invoice_rejected(
    db: Session,
    *,
    case_id: uuid.UUID,
    creator_user_id: uuid.UUID | None,
    actor: User,
    invoice_number: str,
    total_pence: int,
    comment: str | None,
) -> None:
    case_number, matter_title = _case_labels(db, case_id)
    _notify_user(
        db,
        recipient_user_id=creator_user_id,
        actor=actor,
        kind=AlertKind.invoice_rejected,
        context={
            "decider_name": _user_label(actor),
            "case_number": case_number,
            "matter_label": matter_title or case_number or "your matter",
            "invoice_number": invoice_number,
            "amount_gbp": _format_gbp(total_pence),
            "comment": (comment or "").strip(),
        },
    )
