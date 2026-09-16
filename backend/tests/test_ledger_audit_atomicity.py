"""Ledger mutation + audit must share one transaction (client-accounting hygiene)."""

from __future__ import annotations

from sqlalchemy import func, select

from app.ledger_audit import log_ledger_approve, log_ledger_edit, log_ledger_post, log_ledger_reject
from app.ledger_service import (
    approve_ledger_pair,
    post_transaction,
    reject_ledger_pair_unapproved,
    update_ledger_pair_unapproved,
)
from app.models import AuditEvent, LedgerEntry
from app.schemas import LedgerPairUpdate, LedgerPostCreate

from tests.ledger_test_helpers import add_case, add_user, ledger_test_session


def _count_entries(db, pair_id) -> int:
    return int(
        db.execute(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.pair_id == pair_id)).scalar_one()
    )


def _count_audit(db, *, action: str, pair_id) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == action, AuditEvent.entity_id == str(pair_id))
        ).scalar_one()
    )


def _office_pending(db, case_id, user, *, amount_pence: int, description: str):
    return post_transaction(
        case_id,
        LedgerPostCreate(
            description=description,
            amount_pence=amount_pence,
            client_direction=None,
            office_direction="debit",
        ),
        user,
        db,
        force_unapproved=True,
    )


def test_ledger_post_and_audit_roll_back_together() -> None:
    """If anything fails before commit, neither posting nor audit may persist."""
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    payload = LedgerPostCreate(
        description="Atomic post",
        amount_pence=5_000,
        client_direction="credit",
        office_direction=None,
    )
    result = post_transaction(case.id, payload, admin, db)
    log_ledger_post(
        db,
        actor_user_id=admin.id,
        case_id=case.id,
        pair_id=result.pair_id,
        payload=payload,
        is_approved=result.is_approved,
    )
    assert _count_entries(db, result.pair_id) >= 1
    assert _count_audit(db, action="ledger.post", pair_id=result.pair_id) == 1

    db.rollback()

    assert _count_entries(db, result.pair_id) == 0
    assert _count_audit(db, action="ledger.post", pair_id=result.pair_id) == 0


def test_ledger_post_and_audit_commit_together() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    payload = LedgerPostCreate(
        description="Committed post",
        amount_pence=7_500,
        client_direction="credit",
        office_direction=None,
    )
    result = post_transaction(case.id, payload, admin, db)
    log_ledger_post(
        db,
        actor_user_id=admin.id,
        case_id=case.id,
        pair_id=result.pair_id,
        payload=payload,
        is_approved=result.is_approved,
    )
    db.commit()

    assert _count_entries(db, result.pair_id) >= 1
    assert _count_audit(db, action="ledger.post", pair_id=result.pair_id) == 1


def test_legacy_commit_before_audit_leaves_posting_without_audit() -> None:
    """Regression baseline: the old router order (commit then log) can strand money."""
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    payload = LedgerPostCreate(
        description="Split commit",
        amount_pence=1_000,
        client_direction="credit",
        office_direction=None,
    )
    result = post_transaction(case.id, payload, admin, db)
    db.commit()
    # Crash / failure before audit is written:
    db.rollback()

    assert _count_entries(db, result.pair_id) >= 1
    assert _count_audit(db, action="ledger.post", pair_id=result.pair_id) == 0


def test_ledger_approve_audit_rolls_back_with_approval() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    result = _office_pending(db, case.id, admin, amount_pence=2_000, description="Pending approve")
    pair_id = result.pair_id
    db.commit()

    approve_ledger_pair(case.id, pair_id, admin, db)
    log_ledger_approve(db, actor_user_id=admin.id, case_id=case.id, pair_id=pair_id)
    db.rollback()

    assert _count_audit(db, action="ledger.approve", pair_id=pair_id) == 0
    # Approval flag must not stick either
    legs = db.execute(select(LedgerEntry).where(LedgerEntry.pair_id == pair_id)).scalars().all()
    assert legs and all(not e.is_approved for e in legs)


def test_ledger_edit_audit_rolls_back_with_edit() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    result = _office_pending(db, case.id, admin, amount_pence=3_000, description="Pending edit")
    pair_id = result.pair_id
    db.commit()

    patch = LedgerPairUpdate(description="Edited", amount_pence=3_100)
    update_ledger_pair_unapproved(case.id, pair_id, patch, admin, db)
    log_ledger_edit(db, actor_user_id=admin.id, case_id=case.id, pair_id=pair_id, payload=patch)
    db.rollback()

    assert _count_audit(db, action="ledger.edit", pair_id=pair_id) == 0
    legs = db.execute(select(LedgerEntry).where(LedgerEntry.pair_id == pair_id)).scalars().all()
    assert legs and all(e.description == "Pending edit" for e in legs)
    assert legs and all(int(e.amount_pence) == 3_000 for e in legs)


def test_ledger_reject_audit_rolls_back_with_delete() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    result = _office_pending(db, case.id, admin, amount_pence=4_000, description="Pending reject")
    pair_id = result.pair_id
    db.commit()

    reject_ledger_pair_unapproved(case.id, pair_id, admin, db, reject_comment="nope")
    log_ledger_reject(db, actor_user_id=admin.id, case_id=case.id, pair_id=pair_id)
    db.rollback()

    assert _count_audit(db, action="ledger.reject", pair_id=pair_id) == 0
    assert _count_entries(db, pair_id) >= 1  # reject not committed → legs still present
