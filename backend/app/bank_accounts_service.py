"""Firm bank account CRUD and posting validation."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import FirmBankAccount


def _digits_only(raw: str | None) -> str | None:
    if raw is None:
        return None
    digits = re.sub(r"\D+", "", raw.strip())
    return digits or None


def list_bank_accounts(db: Session, *, kind: str | None = None, active_only: bool = False) -> list[FirmBankAccount]:
    q = select(FirmBankAccount).order_by(FirmBankAccount.account_kind, FirmBankAccount.name)
    if kind:
        q = q.where(FirmBankAccount.account_kind == kind)
    if active_only:
        q = q.where(FirmBankAccount.is_active.is_(True))
    return list(db.execute(q).scalars().all())


def get_bank_account(db: Session, account_id: uuid.UUID) -> FirmBankAccount:
    row = db.get(FirmBankAccount, account_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    return row


def active_client_banks(db: Session) -> list[FirmBankAccount]:
    return list_bank_accounts(db, kind="client", active_only=True)


def default_client_bank(db: Session) -> FirmBankAccount | None:
    rows = active_client_banks(db)
    for r in rows:
        if r.is_default:
            return r
    return rows[0] if rows else None


def enforce_client_post_bank_fields(
    db: Session,
    *,
    firm_bank_account_id: uuid.UUID | None,
    payment_method: str | None,
) -> tuple[uuid.UUID | None, str | None]:
    """When client banks are configured, require bank + payment method on actual client posts."""
    banks = active_client_banks(db)
    if not banks:
        return firm_bank_account_id, payment_method
    bank_id = firm_bank_account_id
    if bank_id is None:
        d = default_client_bank(db)
        if d is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Configure a client bank account before posting client money",
            )
        bank_id = d.id
    bank = get_bank_account(db, bank_id)
    if bank.account_kind != "client" or not bank.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="firm_bank_account_id must be an active client bank account",
        )
    if not (payment_method or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="payment_method is required for client account postings",
        )
    return bank.id, payment_method.strip()


def require_client_bank_account(db: Session, account_id: uuid.UUID | None) -> FirmBankAccount:
    if account_id is None:
        d = default_client_bank(db)
        if d is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No client bank account configured",
            )
        return d
    bank = get_bank_account(db, account_id)
    if bank.account_kind != "client" or not bank.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="firm_bank_account_id must be an active client bank account",
        )
    return bank


def create_bank_account(
    db: Session,
    *,
    name: str,
    account_kind: str,
    sort_code: str | None,
    account_number: str | None,
    is_default: bool,
    is_active: bool,
) -> FirmBankAccount:
    kind = "office" if (account_kind or "").strip().lower() == "office" else "client"
    digits = _digits_only(account_number)
    now = datetime.now(timezone.utc)
    row = FirmBankAccount(
        id=uuid.uuid4(),
        name=name.strip(),
        account_kind=kind,
        sort_code=(sort_code or "").strip() or None,
        account_number=digits,
        account_number_last4=digits[-4:] if digits else None,
        is_active=bool(is_active),
        is_default=bool(is_default),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    if row.is_default:
        _clear_other_defaults(db, row)
    return row


def update_bank_account(
    db: Session,
    row: FirmBankAccount,
    *,
    name: str | None = None,
    sort_code: str | None = None,
    account_number: str | None = None,
    is_default: bool | None = None,
    is_active: bool | None = None,
) -> FirmBankAccount:
    if name is not None:
        row.name = name.strip()
    if sort_code is not None:
        row.sort_code = sort_code.strip() or None
    if account_number is not None:
        digits = _digits_only(account_number)
        row.account_number = digits
        row.account_number_last4 = digits[-4:] if digits else None
    if is_active is not None:
        row.is_active = bool(is_active)
    if is_default is not None:
        row.is_default = bool(is_default)
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    if row.is_default:
        _clear_other_defaults(db, row)
    return row


def _clear_other_defaults(db: Session, keep: FirmBankAccount) -> None:
    db.execute(
        update(FirmBankAccount)
        .where(
            FirmBankAccount.account_kind == keep.account_kind,
            FirmBankAccount.id != keep.id,
            FirmBankAccount.is_default.is_(True),
        )
        .values(is_default=False)
    )
