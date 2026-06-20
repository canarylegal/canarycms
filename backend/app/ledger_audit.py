"""Audit logging helpers for ledger postings and invoice lifecycle."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.audit import log_event
from app.ledger_service import get_ledger
from app.schemas import LedgerPairUpdate, LedgerPostCreate


def _directions_label(
    *,
    client_direction: str | None,
    office_direction: str | None,
    amount_pence: int,
) -> str:
    parts: list[str] = []
    if client_direction:
        parts.append(f"client {client_direction}")
    if office_direction:
        parts.append(f"office {office_direction}")
    legs = " / ".join(parts) if parts else "—"
    pounds = abs(amount_pence) / 100
    return f"£{pounds:.2f} ({legs})"


def ledger_post_meta(
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    payload: LedgerPostCreate,
    db: Session,
    *,
    is_approved: bool,
    invoice_number: str | None = None,
) -> dict[str, Any]:
    ledger = get_ledger(case_id, db)
    meta: dict[str, Any] = {
        "case_id": str(case_id),
        "pair_id": str(pair_id),
        "amount_pence": payload.amount_pence,
        "client_direction": payload.client_direction,
        "office_direction": payload.office_direction,
        "description": payload.description,
        "reference": payload.reference,
        "is_approved": is_approved,
        "client_balance_after_pence": ledger.client.balance_pence,
        "office_balance_after_pence": ledger.office.balance_pence,
    }
    if invoice_number:
        meta["invoice_number"] = invoice_number
    return meta


def log_ledger_post(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    payload: LedgerPostCreate,
    is_approved: bool,
    invoice_number: str | None = None,
) -> None:
    meta = ledger_post_meta(
        case_id,
        pair_id,
        payload,
        db,
        is_approved=is_approved,
        invoice_number=invoice_number,
    )
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="ledger.post",
        entity_type="ledger_pair",
        entity_id=str(pair_id),
        meta=meta,
    )


def log_ledger_approve(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
) -> None:
    from sqlalchemy import select

    from app.models import LedgerAccount, LedgerEntry

    accounts = (
        db.execute(select(LedgerAccount).where(LedgerAccount.case_id == case_id)).scalars().all()
    )
    aid = {a.id for a in accounts}
    legs = (
        db.execute(
            select(LedgerEntry).where(
                LedgerEntry.pair_id == pair_id,
                LedgerEntry.account_id.in_(aid),
            )
        )
        .scalars()
        .all()
    )
    client_dir: str | None = None
    office_dir: str | None = None
    amount_pence = 0
    description = ""
    reference: str | None = None
    for leg in legs:
        amount_pence = int(leg.amount_pence)
        description = leg.description or ""
        reference = leg.reference
        acct = next((a for a in accounts if a.id == leg.account_id), None)
        if acct is None:
            continue
        if acct.account_type.value == "client":
            client_dir = leg.direction.value
        elif acct.account_type.value == "office":
            office_dir = leg.direction.value

    ledger = get_ledger(case_id, db)
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="ledger.approve",
        entity_type="ledger_pair",
        entity_id=str(pair_id),
        meta={
            "case_id": str(case_id),
            "pair_id": str(pair_id),
            "amount_pence": amount_pence,
            "client_direction": client_dir,
            "office_direction": office_dir,
            "description": description,
            "reference": reference,
            "client_balance_after_pence": ledger.client.balance_pence,
            "office_balance_after_pence": ledger.office.balance_pence,
        },
    )


def log_invoice_create(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    invoice_id: uuid.UUID,
    invoice_number: str,
    total_pence: int,
    pair_id: uuid.UUID,
) -> None:
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="invoice.create",
        entity_type="case_invoice",
        entity_id=str(invoice_id),
        meta={
            "case_id": str(case_id),
            "invoice_id": str(invoice_id),
            "invoice_number": invoice_number,
            "amount_pence": total_pence,
            "pair_id": str(pair_id),
        },
    )


def log_invoice_approve(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    invoice_id: uuid.UUID,
    invoice_number: str,
    total_pence: int,
    pair_id: uuid.UUID,
) -> None:
    ledger = get_ledger(case_id, db)
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="invoice.approve",
        entity_type="case_invoice",
        entity_id=str(invoice_id),
        meta={
            "case_id": str(case_id),
            "invoice_id": str(invoice_id),
            "invoice_number": invoice_number,
            "amount_pence": total_pence,
            "pair_id": str(pair_id),
            "client_balance_after_pence": ledger.client.balance_pence,
            "office_balance_after_pence": ledger.office.balance_pence,
        },
    )


def log_invoice_void(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    invoice_id: uuid.UUID,
    invoice_number: str,
    total_pence: int,
    was_pending: bool,
    reversal_pair_id: uuid.UUID | None = None,
) -> None:
    meta: dict[str, Any] = {
        "case_id": str(case_id),
        "invoice_id": str(invoice_id),
        "invoice_number": invoice_number,
        "amount_pence": total_pence,
        "was_pending": was_pending,
    }
    if reversal_pair_id:
        meta["reversal_pair_id"] = str(reversal_pair_id)
        ledger = get_ledger(case_id, db)
        meta["client_balance_after_pence"] = ledger.client.balance_pence
        meta["office_balance_after_pence"] = ledger.office.balance_pence
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="invoice.void",
        entity_type="case_invoice",
        entity_id=str(invoice_id),
        meta=meta,
    )


def format_amount_pence(amount_pence: Any) -> str:
    try:
        p = int(amount_pence)
    except (TypeError, ValueError):
        return "£0.00"
    neg = p < 0
    return f"{'-' if neg else ''}£{abs(p) / 100:.2f}"


def format_ledger_directions(meta: dict[str, Any]) -> str:
    return _directions_label(
        client_direction=meta.get("client_direction"),
        office_direction=meta.get("office_direction"),
        amount_pence=int(meta.get("amount_pence") or 0),
    )


def log_ledger_edit(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
    payload: LedgerPairUpdate,
) -> None:
    meta: dict[str, Any] = {
        "case_id": str(case_id),
        "pair_id": str(pair_id),
    }
    if payload.amount_pence is not None:
        meta["amount_pence"] = payload.amount_pence
    if payload.description is not None:
        meta["description"] = payload.description
    if payload.reference is not None:
        meta["reference"] = payload.reference
    if payload.anticipated_for_date is not None:
        meta["anticipated_for_date"] = payload.anticipated_for_date.isoformat()
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="ledger.edit",
        entity_type="ledger_pair",
        entity_id=str(pair_id),
        meta=meta,
    )


def log_ledger_reject(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    pair_id: uuid.UUID,
) -> None:
    log_event(
        db,
        actor_user_id=actor_user_id,
        action="ledger.reject",
        entity_type="ledger_pair",
        entity_id=str(pair_id),
        meta={"case_id": str(case_id), "pair_id": str(pair_id)},
    )
