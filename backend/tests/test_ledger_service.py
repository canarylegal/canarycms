"""Tests for ledger posting, balances, and SAR no-deficit enforcement."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.ledger_service import (
    approve_ledger_pair,
    get_ledger,
    post_transaction,
    reject_ledger_pair_unapproved,
    update_ledger_pair_unapproved,
)
from app.models import UserPermissionCategory, UserRole
from app.reports_service import balances_by_case_ids
from app.schemas import LedgerPairUpdate, LedgerPostCreate

from tests.ledger_test_helpers import add_case, add_cashier_category, add_user, ledger_test_session


def _post(
    db,
    case_id,
    user,
    *,
    amount_pence: int,
    client_direction: str | None = None,
    office_direction: str | None = None,
    force_unapproved: bool = False,
    anticipated: bool = False,
) -> uuid.UUID:
    anticipated_for_date = date(2026, 6, 15) if anticipated else None
    return post_transaction(
        case_id,
        LedgerPostCreate(
            description="Test posting",
            amount_pence=amount_pence,
            client_direction=client_direction,
            office_direction=office_direction,
            anticipated=anticipated,
            anticipated_for_date=anticipated_for_date,
        ),
        user,
        db,
        force_unapproved=force_unapproved,
    ).pair_id


def test_client_credit_increases_balance() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=12_345, client_direction="credit")
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 12_345
    assert ledger.office.balance_pence == 0

    firm_totals = balances_by_case_ids([case.id], db)
    assert firm_totals[case.id] == (12_345, 0)


def test_client_debit_after_credit_updates_balance_exactly() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=10_000, client_direction="credit")
    _post(db, case.id, admin, amount_pence=4_000, client_direction="debit")
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 6_000


def test_transfer_client_to_office() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=20_000, client_direction="credit")
    _post(
        db,
        case.id,
        admin,
        amount_pence=7_500,
        client_direction="debit",
        office_direction="credit",
    )
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 12_500
    assert ledger.office.balance_pence == 7_500


def test_sar_rejects_client_debit_into_deficit() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    with pytest.raises(HTTPException) as exc:
        _post(db, case.id, admin, amount_pence=100, client_direction="debit")
    assert exc.value.status_code == 422
    assert "deficit" in str(exc.value.detail).lower()

    db.rollback()
    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 0


def test_pending_client_debit_does_not_affect_balance_until_approved() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=5_000, client_direction="credit")
    pair_id = _post(
        db,
        case.id,
        cashier,
        amount_pence=9_000,
        client_direction="debit",
        force_unapproved=True,
    )
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 5_000

    with pytest.raises(HTTPException) as exc:
        approve_ledger_pair(case.id, pair_id, cashier, db)
    assert exc.value.status_code == 422
    assert "deficit" in str(exc.value.detail).lower()

    db.rollback()


def test_approve_valid_pending_posting_updates_balance() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=10_000, client_direction="credit")
    pair_id = _post(
        db,
        case.id,
        cashier,
        amount_pence=3_000,
        client_direction="debit",
        force_unapproved=True,
    )
    db.commit()

    approve_ledger_pair(case.id, pair_id, cashier, db)
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 7_000


def test_integer_pence_balance_is_exact_after_many_postings() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    net = 0
    for amount in (1, 99, 10_000, 33, 2_147_483_647 % 100_000):
        _post(db, case.id, admin, amount_pence=amount, client_direction="credit")
        net += amount
    for amount in (50, 1_234):
        _post(db, case.id, admin, amount_pence=amount, client_direction="debit")
        net -= amount
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == net


def test_any_user_may_post_anticipated_without_post_permissions() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    readonly = UserPermissionCategory(
        id=uuid.uuid4(),
        name="Read only",
        perm_fee_earner=True,
        perm_post_client=False,
        perm_post_office=False,
        perm_approve_payments=False,
        perm_approve_invoices=False,
        perm_admin=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(readonly)
    db.commit()
    secretary = add_user(db, role=UserRole.user, permission_category_id=readonly.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    pair_id = _post(
        db,
        case.id,
        secretary,
        amount_pence=4_000,
        client_direction="credit",
        anticipated=True,
    )
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 0
    assert any(e.pair_id == pair_id and e.is_anticipated for e in ledger.entries)


def test_anticipated_posting_affects_balance_after_post_permission_approval() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    readonly = UserPermissionCategory(
        id=uuid.uuid4(),
        name="Read only",
        perm_fee_earner=True,
        perm_post_client=False,
        perm_post_office=False,
        perm_approve_payments=False,
        perm_approve_invoices=False,
        perm_admin=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(readonly)
    db.commit()
    cat = add_cashier_category(db)
    poster = add_user(db, role=UserRole.user, permission_category_id=readonly.id)
    approver = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    pair_id = _post(
        db,
        case.id,
        poster,
        amount_pence=6_500,
        client_direction="credit",
        anticipated=True,
    )
    db.commit()

    approve_ledger_pair(case.id, pair_id, approver, db)
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 6_500
    assert all(not e.is_anticipated for e in ledger.entries if e.pair_id == pair_id)


def test_cashier_may_edit_anticipated_office_debit_before_approval() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    pair_id = _post(
        db,
        case.id,
        admin,
        amount_pence=150,
        office_direction="debit",
        anticipated=True,
    )
    db.commit()

    update_ledger_pair_unapproved(
        case.id,
        pair_id,
        LedgerPairUpdate(amount_pence=200, description="DocuSign — revised"),
        cashier,
        db,
    )
    db.commit()

    ledger = get_ledger(case.id, db)
    legs = [e for e in ledger.entries if e.pair_id == pair_id]
    assert len(legs) == 1
    assert legs[0].amount_pence == 200
    assert legs[0].description == "DocuSign — revised"
    assert ledger.office.balance_pence == 0

    approve_ledger_pair(case.id, pair_id, cashier, db)
    db.commit()
    assert get_ledger(case.id, db).office.balance_pence == -200


def test_cashier_may_reject_anticipated_posting() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    pair_id = _post(
        db,
        case.id,
        admin,
        amount_pence=150,
        office_direction="debit",
        anticipated=True,
    )
    db.commit()

    reject_ledger_pair_unapproved(case.id, pair_id, cashier, db)
    db.commit()

    ledger = get_ledger(case.id, db)
    assert not any(e.pair_id == pair_id for e in ledger.entries)
