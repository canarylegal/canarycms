"""Extensive ledger invariant, SAR deficit, and edge-case tests."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.ledger_service import (
    _balance,
    _get_or_create_accounts,
    approve_ledger_pair,
    delete_ledger_pair_unapproved,
    get_ledger,
    post_transaction,
    reject_ledger_pair_unapproved,
    update_ledger_pair_unapproved,
)
from app.models import LedgerAccount, LedgerAccountType, LedgerDirection, LedgerEntry, UserRole
from app.schemas import LedgerPairUpdate, LedgerPostCreate

from tests.ledger_test_helpers import add_case, add_cashier_category, add_fee_earner_category, add_user, ledger_test_session


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
    description: str = "Test posting",
    reference: str | None = None,
) -> uuid.UUID:
    anticipated_for_date = date(2026, 6, 15) if anticipated else None
    return post_transaction(
        case_id,
        LedgerPostCreate(
            description=description,
            amount_pence=amount_pence,
            client_direction=client_direction,
            office_direction=office_direction,
            anticipated=anticipated,
            anticipated_for_date=anticipated_for_date,
            reference=reference,
        ),
        user,
        db,
        force_unapproved=force_unapproved,
    ).pair_id


def test_unique_constraint_on_ledger_account_model() -> None:
    names = {c.name for c in LedgerAccount.__table__.constraints if getattr(c, "name", None)}
    assert "uq_ledger_account_case_type" in names


def test_get_or_create_accounts_idempotent() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    a1 = _get_or_create_accounts(case.id, db)
    a2 = _get_or_create_accounts(case.id, db)
    assert a1["client"].id == a2["client"].id
    assert a1["office"].id == a2["office"].id
    rows = db.execute(select(LedgerAccount).where(LedgerAccount.case_id == case.id)).scalars().all()
    assert len(rows) == 2
    types = {r.account_type for r in rows}
    assert types == {LedgerAccountType.client, LedgerAccountType.office}


def test_balance_sql_sum_matches_manual_iteration() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=10_000, client_direction="credit")
    _post(db, case.id, admin, amount_pence=2_500, client_direction="debit")
    _post(db, case.id, admin, amount_pence=100, client_direction="credit")
    db.commit()

    accounts = _get_or_create_accounts(case.id, db)
    sql_bal = _balance(accounts["client"].id, db, approved_only=True)
    entries = (
        db.execute(
            select(LedgerEntry).where(
                LedgerEntry.account_id == accounts["client"].id,
                LedgerEntry.is_approved.is_(True),
            )
        )
        .scalars()
        .all()
    )
    manual = 0
    for e in entries:
        manual += e.amount_pence if e.direction == LedgerDirection.credit else -e.amount_pence
    assert sql_bal == manual == 7_600


def test_exact_zero_client_balance_debit_of_entire_credit_allowed() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=5_000, client_direction="credit")
    _post(db, case.id, admin, amount_pence=5_000, client_direction="debit")
    db.commit()
    assert get_ledger(case.id, db).client.balance_pence == 0


def test_one_penny_over_balance_rejected() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=100, client_direction="credit")
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _post(db, case.id, admin, amount_pence=101, client_direction="debit")
    assert exc.value.status_code == 422
    db.rollback()
    assert get_ledger(case.id, db).client.balance_pence == 100


def test_deficit_rejection_leaves_no_orphan_legs() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    with pytest.raises(HTTPException):
        _post(db, case.id, admin, amount_pence=1, client_direction="debit")
    db.rollback()
    accounts = _get_or_create_accounts(case.id, db)
    legs = db.execute(select(LedgerEntry).where(LedgerEntry.account_id == accounts["client"].id)).scalars().all()
    assert legs == []


def test_office_only_debit_does_not_check_client_deficit() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=99_999, office_direction="debit")
    db.commit()
    ledger = get_ledger(case.id, db)
    assert ledger.client.balance_pence == 0
    assert ledger.office.balance_pence == -99_999


def test_double_entry_pair_has_matching_amount_on_both_legs() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=8_000, client_direction="credit")
    pair = _post(
        db,
        case.id,
        admin,
        amount_pence=3_000,
        client_direction="debit",
        office_direction="credit",
    )
    db.commit()
    legs = [e for e in get_ledger(case.id, db).entries if e.pair_id == pair]
    assert len(legs) == 2
    assert {e.amount_pence for e in legs} == {3_000}
    dirs = {(e.account_type, e.direction) for e in legs}
    assert dirs == {("client", "debit"), ("office", "credit")}


def test_requires_at_least_one_direction() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    with pytest.raises(HTTPException) as exc:
        post_transaction(
            case.id,
            LedgerPostCreate(description="noop", amount_pence=100),
            admin,
            db,
        )
    assert exc.value.status_code == 422


def test_sequential_near_miss_debits_never_go_negative() -> None:
    """Simulate contended spend: credit once, then many maxed debits sequentially."""
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    credit = 10_000
    _post(db, case.id, admin, amount_pence=credit, client_direction="credit")
    db.commit()

    successes = 0
    failures = 0
    for _ in range(25):
        bal = get_ledger(case.id, db).client.balance_pence
        try:
            _post(db, case.id, admin, amount_pence=credit, client_direction="debit")
            db.commit()
            successes += 1
        except HTTPException as exc:
            assert exc.status_code == 422
            db.rollback()
            failures += 1
            assert bal < credit or bal == 0 or successes >= 1

    assert successes == 1
    assert failures == 24
    assert get_ledger(case.id, db).client.balance_pence == 0


def test_many_tiny_credits_and_debits_net_exact() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    net = 0
    for i in range(1, 201):
        _post(db, case.id, admin, amount_pence=i, client_direction="credit")
        net += i
        if i % 3 == 0:
            debit = min(i // 2, net)
            if debit > 0:
                _post(db, case.id, admin, amount_pence=debit, client_direction="debit")
                net -= debit
    db.commit()
    assert get_ledger(case.id, db).client.balance_pence == net
    assert net >= 0


def test_approve_deficit_does_not_flip_is_approved() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=1_000, client_direction="credit")
    pair = _post(
        db,
        case.id,
        cashier,
        amount_pence=5_000,
        client_direction="debit",
        force_unapproved=True,
    )
    db.commit()

    with pytest.raises(HTTPException) as e:
        approve_ledger_pair(case.id, pair, cashier, db)
    assert e.value.status_code == 422
    db.rollback()

    ledger = get_ledger(case.id, db)
    legs = [x for x in ledger.entries if x.pair_id == pair]
    assert legs and all(not x.is_approved for x in legs)
    assert ledger.client.balance_pence == 1_000


def test_concurrent_style_two_pending_approvals_only_one_fits() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)

    _post(db, case.id, admin, amount_pence=10_000, client_direction="credit")
    p1 = _post(db, case.id, cashier, amount_pence=7_000, client_direction="debit", force_unapproved=True)
    p2 = _post(db, case.id, cashier, amount_pence=7_000, client_direction="debit", force_unapproved=True)
    db.commit()

    approve_ledger_pair(case.id, p1, cashier, db)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        approve_ledger_pair(case.id, p2, cashier, db)
    assert exc.value.status_code == 422
    db.rollback()
    assert get_ledger(case.id, db).client.balance_pence == 3_000


def test_cannot_approve_twice() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=2_000, client_direction="credit")
    pair = _post(db, case.id, cashier, amount_pence=500, client_direction="debit", force_unapproved=True)
    db.commit()
    approve_ledger_pair(case.id, pair, cashier, db)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        approve_ledger_pair(case.id, pair, cashier, db)
    assert exc.value.status_code == 400


def test_cannot_edit_or_reject_approved() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    pair = _post(db, case.id, admin, amount_pence=1_000, client_direction="credit")
    db.commit()
    with pytest.raises(HTTPException) as e1:
        update_ledger_pair_unapproved(case.id, pair, LedgerPairUpdate(amount_pence=2), admin, db)
    assert e1.value.status_code == 400
    with pytest.raises(HTTPException) as e2:
        reject_ledger_pair_unapproved(case.id, pair, admin, db)
    assert e2.value.status_code == 400


def test_delete_unapproved_pair_removes_both_legs() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    pair = _post(
        db,
        case.id,
        admin,
        amount_pence=1_000,
        client_direction="debit",
        office_direction="credit",
        force_unapproved=True,
    )
    db.commit()
    delete_ledger_pair_unapproved(case.id, pair, db)
    db.commit()
    assert not any(e.pair_id == pair for e in get_ledger(case.id, db).entries)


def test_unapproved_does_not_affect_approved_only_balance() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=4_000, client_direction="credit")
    _post(db, case.id, admin, amount_pence=50_000, client_direction="debit", force_unapproved=True)
    db.commit()
    accounts = _get_or_create_accounts(case.id, db)
    assert _balance(accounts["client"].id, db, approved_only=True) == 4_000
    assert _balance(accounts["client"].id, db, approved_only=False) == 4_000 - 50_000


def test_reference_and_description_persisted() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    pair = _post(
        db,
        case.id,
        admin,
        amount_pence=250,
        client_direction="credit",
        description="Client receipt",
        reference="CHQ-99",
    )
    db.commit()
    legs = [e for e in get_ledger(case.id, db).entries if e.pair_id == pair]
    assert legs[0].description == "Client receipt"
    assert legs[0].reference == "CHQ-99"


def test_office_credit_increases_office_balance() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    _post(db, case.id, admin, amount_pence=1_500, office_direction="credit")
    db.commit()
    assert get_ledger(case.id, db).office.balance_pence == 1_500


def test_large_amount_within_int_range() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    big = 2_000_000_000  # £20m in pence
    _post(db, case.id, admin, amount_pence=big, client_direction="credit")
    _post(db, case.id, admin, amount_pence=big - 1, client_direction="debit")
    db.commit()
    assert get_ledger(case.id, db).client.balance_pence == 1


def test_pending_suffix_stripped_on_approve() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_cashier_category(db)
    cashier = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)
    pair = post_transaction(
        case.id,
        LedgerPostCreate(
            description="Invoice INV-1 (pending approval)",
            amount_pence=2_000,
            office_direction="debit",
        ),
        admin,
        db,
        force_unapproved=True,
    ).pair_id
    db.commit()
    approve_ledger_pair(case.id, pair, cashier, db)
    db.commit()
    legs = [e for e in get_ledger(case.id, db).entries if e.pair_id == pair]
    assert legs[0].description == "Invoice INV-1"
    assert legs[0].is_approved is True


def test_get_ledger_orders_by_posted_at() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    for amt in (100, 200, 300):
        _post(db, case.id, admin, amount_pence=amt, client_direction="credit")
    db.commit()
    entries = get_ledger(case.id, db).entries
    assert [e.amount_pence for e in entries] == [100, 200, 300]


def test_fee_earner_cannot_post_actual_without_post_rights() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    cat = add_fee_earner_category(db)
    fe = add_user(db, role=UserRole.user, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=admin.id)
    with pytest.raises(HTTPException) as exc:
        _post(db, case.id, fe, amount_pence=100, client_direction="credit", anticipated=False)
    assert exc.value.status_code == 403


def test_accounts_created_under_for_update_path() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    accounts = _get_or_create_accounts(case.id, db, for_update=True)
    assert "client" in accounts and "office" in accounts
    _post(db, case.id, admin, amount_pence=50, client_direction="credit")
    db.commit()
    assert get_ledger(case.id, db).client.balance_pence == 50
