"""Client account month-end reconciliation snapshots."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.models import Case, ClientAccountReconciliation, FirmSettings, ReconciliationStatus, User
from app.reports_service import balances_by_case_ids
from app.permission_checks import user_may_approve_ledger


def firm_wide_ledger_totals(db: Session) -> tuple[int, int]:
    """Sum approved client and office ledger balances across all matters."""
    case_ids = list(db.execute(select(Case.id)).scalars().all())
    if not case_ids:
        return 0, 0
    bal = balances_by_case_ids(case_ids, db)
    client_total = office_total = 0
    for cid in case_ids:
        cp, op = bal.get(cid, (0, 0))
        client_total += cp
        office_total += op
    return client_total, office_total


def compute_difference_pence(*, bank_statement_balance_pence: int, ledger_client_total_pence: int) -> int:
    return int(bank_statement_balance_pence) - int(ledger_client_total_pence)


def _user_label(db: Session, user_id: uuid.UUID | None) -> str | None:
    if not user_id:
        return None
    u = db.get(User, user_id)
    if not u:
        return None
    return (u.display_name or u.email or "").strip() or None


def reconciliation_to_dict(row: ClientAccountReconciliation, db: Session) -> dict:
    return {
        "id": str(row.id),
        "period_end_date": row.period_end_date.isoformat(),
        "ledger_client_total_pence": row.ledger_client_total_pence,
        "ledger_office_total_pence": row.ledger_office_total_pence,
        "bank_statement_balance_pence": row.bank_statement_balance_pence,
        "difference_pence": row.difference_pence,
        "prepared_by_user_id": str(row.prepared_by_user_id),
        "prepared_by_name": _user_label(db, row.prepared_by_user_id),
        "prepared_at": row.prepared_at.isoformat() if row.prepared_at else None,
        "approved_by_user_id": str(row.approved_by_user_id) if row.approved_by_user_id else None,
        "approved_by_name": _user_label(db, row.approved_by_user_id),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "notes": row.notes,
        "status": row.status.value,
    }


def list_reconciliations(db: Session, *, limit: int = 48) -> list[ClientAccountReconciliation]:
    return list(
        db.execute(
            select(ClientAccountReconciliation)
            .order_by(ClientAccountReconciliation.period_end_date.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def get_reconciliation_for_period(db: Session, period_end_date: date) -> ClientAccountReconciliation | None:
    return db.execute(
        select(ClientAccountReconciliation).where(ClientAccountReconciliation.period_end_date == period_end_date)
    ).scalar_one_or_none()


def get_reconciliation(db: Session, rec_id: uuid.UUID) -> ClientAccountReconciliation:
    row = db.get(ClientAccountReconciliation, rec_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reconciliation not found.")
    return row


def _assert_draft(row: ClientAccountReconciliation) -> None:
    if row.status != ReconciliationStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reconciliation is approved and cannot be changed.",
        )


def _assert_approvable(*, difference_pence: int, notes: str | None) -> None:
    if difference_pence != 0 and not (notes or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter notes explaining the difference before approving.",
        )


def create_reconciliation(
    db: Session,
    *,
    actor: User,
    period_end_date: date,
    bank_statement_balance_pence: int,
    notes: str | None,
) -> ClientAccountReconciliation:
    existing = db.execute(
        select(ClientAccountReconciliation).where(ClientAccountReconciliation.period_end_date == period_end_date)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A reconciliation already exists for that period end date.",
        )
    client_total, office_total = firm_wide_ledger_totals(db)
    diff = compute_difference_pence(
        bank_statement_balance_pence=bank_statement_balance_pence,
        ledger_client_total_pence=client_total,
    )
    now = datetime.now(timezone.utc)
    row = ClientAccountReconciliation(
        period_end_date=period_end_date,
        ledger_client_total_pence=client_total,
        ledger_office_total_pence=office_total,
        bank_statement_balance_pence=bank_statement_balance_pence,
        difference_pence=diff,
        prepared_by_user_id=actor.id,
        prepared_at=now,
        notes=(notes or "").strip() or None,
        status=ReconciliationStatus.draft,
    )
    db.add(row)
    db.flush()
    log_event(
        db,
        actor_user_id=actor.id,
        action="reconciliation.create",
        entity_type="client_account_reconciliation",
        entity_id=str(row.id),
        meta={
            "period_end_date": period_end_date.isoformat(),
            "ledger_client_total_pence": client_total,
            "bank_statement_balance_pence": bank_statement_balance_pence,
            "difference_pence": diff,
        },
    )
    return row


def update_reconciliation(
    db: Session,
    *,
    actor: User,
    row: ClientAccountReconciliation,
    bank_statement_balance_pence: int | None = None,
    notes: str | None = None,
    refresh_ledger_totals: bool = True,
) -> ClientAccountReconciliation:
    _assert_draft(row)
    if refresh_ledger_totals:
        client_total, office_total = firm_wide_ledger_totals(db)
        row.ledger_client_total_pence = client_total
        row.ledger_office_total_pence = office_total
    if bank_statement_balance_pence is not None:
        row.bank_statement_balance_pence = bank_statement_balance_pence
    if notes is not None:
        row.notes = notes.strip() or None
    row.difference_pence = compute_difference_pence(
        bank_statement_balance_pence=row.bank_statement_balance_pence,
        ledger_client_total_pence=row.ledger_client_total_pence,
    )
    row.prepared_by_user_id = actor.id
    row.prepared_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    log_event(
        db,
        actor_user_id=actor.id,
        action="reconciliation.update",
        entity_type="client_account_reconciliation",
        entity_id=str(row.id),
        meta={
            "period_end_date": row.period_end_date.isoformat(),
            "ledger_client_total_pence": row.ledger_client_total_pence,
            "bank_statement_balance_pence": row.bank_statement_balance_pence,
            "difference_pence": row.difference_pence,
        },
    )
    return row


def approve_reconciliation(db: Session, *, actor: User, row: ClientAccountReconciliation) -> ClientAccountReconciliation:
    _assert_draft(row)
    if not user_may_approve_ledger(actor, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not permitted to approve reconciliations.",
        )
    _assert_approvable(difference_pence=row.difference_pence, notes=row.notes)
    now = datetime.now(timezone.utc)
    row.status = ReconciliationStatus.approved
    row.approved_by_user_id = actor.id
    row.approved_at = now
    db.add(row)
    db.flush()
    log_event(
        db,
        actor_user_id=actor.id,
        action="reconciliation.approve",
        entity_type="client_account_reconciliation",
        entity_id=str(row.id),
        meta={
            "period_end_date": row.period_end_date.isoformat(),
            "ledger_client_total_pence": row.ledger_client_total_pence,
            "bank_statement_balance_pence": row.bank_statement_balance_pence,
            "difference_pence": row.difference_pence,
        },
    )
    return row


def firm_settings_for_report(db: Session) -> FirmSettings:
    row = db.get(FirmSettings, 1)
    if row is None:
        row = FirmSettings(id=1)
        db.add(row)
        db.flush()
    return row
