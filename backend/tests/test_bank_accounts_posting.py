"""Client bank + payment method enforcement on ledger posts."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.bank_accounts_service import create_bank_account
from app.ledger_service import get_ledger, post_transaction
from app.models import UserRole
from app.schemas import LedgerPostCreate
from tests.ledger_test_helpers import (
    add_case,
    add_fee_earner_category,
    add_user,
    ledger_test_session,
)


def test_client_post_without_banks_still_works() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    post_transaction(
        case.id,
        LedgerPostCreate(
            description="Receipt",
            amount_pence=10_000,
            client_direction="credit",
            contact_label="N/A",
        ),
        user,
        db,
    )
    assert get_ledger(case.id, db).client.balance_pence == 10_000


def test_client_post_requires_method_when_bank_configured() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    create_bank_account(
        db,
        name="Client account",
        account_kind="client",
        sort_code="12-34-56",
        account_number="12345678",
        is_default=True,
        is_active=True,
    )
    db.commit()
    with pytest.raises(HTTPException) as ei:
        post_transaction(
            case.id,
            LedgerPostCreate(
                description="Receipt",
                amount_pence=10_000,
                client_direction="credit",
                contact_label="N/A",
            ),
            user,
            db,
        )
    assert ei.value.status_code == 422
    assert "payment_method" in str(ei.value.detail)


def test_client_post_with_bank_and_method_ok() -> None:
    db = ledger_test_session()
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    bank = create_bank_account(
        db,
        name="Client account",
        account_kind="client",
        sort_code="12-34-56",
        account_number="12345678",
        is_default=True,
        is_active=True,
    )
    db.commit()
    post_transaction(
        case.id,
        LedgerPostCreate(
            description="Receipt",
            amount_pence=25_000,
            client_direction="credit",
            contact_label="N/A",
            firm_bank_account_id=bank.id,
            payment_method="faster_payments",
        ),
        user,
        db,
    )
    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 25_000
    client_legs = [e for e in ledger.entries if e.account_type == "client"]
    assert client_legs[0].firm_bank_account_id == bank.id
    assert client_legs[0].payment_method == "faster_payments"


def test_anticipated_client_post_skips_bank_requirement() -> None:
    db = ledger_test_session()
    cat = add_fee_earner_category(db)
    user = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=user.id)
    create_bank_account(
        db,
        name="Client account",
        account_kind="client",
        sort_code=None,
        account_number=None,
        is_default=True,
        is_active=True,
    )
    db.commit()
    post_transaction(
        case.id,
        LedgerPostCreate(
            description="Anticipated out",
            amount_pence=5_000,
            client_direction="debit",
            contact_label="N/A",
            anticipated=True,
            anticipated_for_date=date.today(),
        ),
        user,
        db,
    )
    assert get_ledger(case.id, db).client.balance_pence == 0
