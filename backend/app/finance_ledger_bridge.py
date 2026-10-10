"""Bridge Finance worksheet lines → ledger anticipated/actual posts."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ledger_service import post_transaction
from app.models import FinanceCategory, FinanceItem, User
from app.schemas import LedgerPostCreate
from app.schemas.bank import FinanceLedgerBridgeIn, FinanceLedgerBridgeOut


def post_finance_items_to_ledger(
    db: Session,
    *,
    case_id: uuid.UUID,
    payload: FinanceLedgerBridgeIn,
    user: User,
) -> FinanceLedgerBridgeOut:
    ant_date = payload.anticipated_for_date
    if payload.anticipated and ant_date is None:
        ant_date = date.today() + timedelta(days=14)

    pair_ids: list[uuid.UUID] = []
    for item_id in payload.item_ids:
        item = db.get(FinanceItem, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Finance item {item_id} not found")
        cat = db.get(FinanceCategory, item.category_id)
        if cat is None or cat.case_id != case_id:
            raise HTTPException(status_code=400, detail="Finance item is not on this matter")
        if cat.credit_only or (item.direction or "").lower() == "credit":
            continue
        amount = int(item.amount_pence or 0) + int(item.vat_pence or 0)
        if amount <= 0:
            continue
        post = LedgerPostCreate(
            description=(item.name or "Finance item").strip()[:500],
            amount_pence=amount,
            client_direction="debit" if payload.ledger_account == "client" else None,
            office_direction="debit" if payload.ledger_account == "office" else None,
            anticipated=bool(payload.anticipated),
            anticipated_for_date=ant_date if payload.anticipated else None,
            firm_bank_account_id=payload.firm_bank_account_id,
            payment_method=payload.payment_method,
            contact_label="N/A",
        )
        result = post_transaction(case_id, post, user, db)
        pair_ids.append(result.pair_id)
    if not pair_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No debit finance items with a positive amount to post",
        )
    return FinanceLedgerBridgeOut(posted_count=len(pair_ids), pair_ids=pair_ids)
