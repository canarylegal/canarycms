"""Invoice allocation and paid_at."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
import pytest

from app.invoice_allocation_service import allocate_to_invoice
from app.ledger_service import post_transaction
from app.models import CaseInvoice
from app.schemas import LedgerPostCreate
from tests.ledger_test_helpers import add_case, add_cashier_category, add_user, ledger_test_session


def test_allocate_marks_paid_when_full() -> None:
    db = ledger_test_session()
    cat = add_cashier_category(db)
    user = add_user(db, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=user.id)
    result = post_transaction(
        case.id,
        LedgerPostCreate(
            description="Office receipt",
            amount_pence=12_000,
            office_direction="credit",
            contact_label="N/A",
        ),
        user,
        db,
    )
    inv = CaseInvoice(
        id=uuid.uuid4(),
        case_id=case.id,
        invoice_number="INV-TEST-1",
        status="approved",
        total_pence=12_000,
        amount_allocated_pence=0,
        created_by_user_id=user.id,
        approved_by_user_id=user.id,
        approved_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()

    allocate_to_invoice(
        db,
        invoice_id=inv.id,
        ledger_pair_id=result.pair_id,
        amount_pence=12_000,
        actor=user,
    )
    db.refresh(inv)
    assert inv.amount_allocated_pence == 12_000
    assert inv.paid_at is not None


def test_allocate_rejects_over_remaining() -> None:
    db = ledger_test_session()
    cat = add_cashier_category(db)
    user = add_user(db, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=user.id)
    result = post_transaction(
        case.id,
        LedgerPostCreate(
            description="Office receipt",
            amount_pence=5_000,
            office_direction="credit",
            contact_label="N/A",
        ),
        user,
        db,
    )
    inv = CaseInvoice(
        id=uuid.uuid4(),
        case_id=case.id,
        invoice_number="INV-TEST-2",
        status="approved",
        total_pence=5_000,
        amount_allocated_pence=0,
        created_by_user_id=user.id,
        approved_by_user_id=user.id,
        approved_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        allocate_to_invoice(
            db,
            invoice_id=inv.id,
            ledger_pair_id=result.pair_id,
            amount_pence=5_001,
            actor=user,
        )
    assert ei.value.status_code == 400
