"""Admin: firm bank accounts."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.bank_accounts_service import (
    create_bank_account,
    get_bank_account,
    list_bank_accounts,
    update_bank_account,
)
from app.db import get_db
from app.deps import require_admin
from app.models import User
from app.schemas.bank import FirmBankAccountCreate, FirmBankAccountOut, FirmBankAccountUpdate

router = APIRouter(prefix="/admin/bank-accounts", tags=["admin-bank-accounts"])


def _out(row) -> FirmBankAccountOut:
    return FirmBankAccountOut(
        id=row.id,
        name=row.name,
        account_kind=row.account_kind,  # type: ignore[arg-type]
        sort_code=row.sort_code,
        account_number=row.account_number,
        account_number_last4=row.account_number_last4,
        is_active=row.is_active,
        is_default=row.is_default,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[FirmBankAccountOut])
def admin_list_bank_accounts(
    kind: str | None = None,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[FirmBankAccountOut]:
    return [_out(r) for r in list_bank_accounts(db, kind=kind)]


@router.post("", response_model=FirmBankAccountOut)
def admin_create_bank_account(
    payload: FirmBankAccountCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FirmBankAccountOut:
    row = create_bank_account(
        db,
        name=payload.name,
        account_kind=payload.account_kind,
        sort_code=payload.sort_code,
        account_number=payload.account_number,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/{account_id}", response_model=FirmBankAccountOut)
def admin_update_bank_account(
    account_id: uuid.UUID,
    payload: FirmBankAccountUpdate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FirmBankAccountOut:
    row = get_bank_account(db, account_id)
    data = payload.model_dump(exclude_unset=True)
    row = update_bank_account(db, row, **data)
    db.commit()
    db.refresh(row)
    return _out(row)
