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


def allocation_fixture(db=None):
    db = db or ledger_test_session()
    from app.models import UserPermissionCategory
    cat = UserPermissionCategory(name=f"Allocation cashier {uuid.uuid4()}", perm_approve_payments=True)
    db.add(cat)
    db.flush()
    user = add_user(db, permission_category_id=cat.id)
    case = add_case(db, fee_earner_user_id=user.id)
    receipt = post_transaction(case.id, LedgerPostCreate(description='Receipt', amount_pence=10000,
        office_direction='credit', contact_label='N/A'), user, db)
    inv = new_invoice(db, case.id, user.id)
    db.commit()
    return db, user, case, inv, receipt.pair_id


def new_invoice(db, case_id, user_id):
    inv = CaseInvoice(id=uuid.uuid4(), case_id=case_id, invoice_number=f'TEST-{uuid.uuid4()}',
        status='approved', total_pence=10000, amount_allocated_pence=0, created_by_user_id=user_id)
    db.add(inv)
    db.flush()
    return inv


def allocate(db, user, inv, pair, amount=6000, **kwargs):
    return allocate_to_invoice(db, invoice_id=inv.id, ledger_pair_id=pair,
        amount_pence=amount, actor=user, **kwargs)


def test_receipt_capacity_shared_between_invoices():
    db, user, case, inv, pair = allocation_fixture()
    second = new_invoice(db, case.id, user.id)
    allocate(db, user, inv, pair)
    with pytest.raises(HTTPException, match='unallocated value'):
        allocate(db, user, second, pair, 4001)
    allocate(db, user, second, pair, 4000)
    assert inv.amount_allocated_pence == 6000 and inv.paid_at is None
    assert second.amount_allocated_pence == 4000


@pytest.mark.parametrize('amount', [0, -1, True, 1.5, '10'])
def test_invalid_amount_has_no_effect(amount):
    db, user, _, inv, pair = allocation_fixture()
    with pytest.raises(HTTPException):
        allocate(db, user, inv, pair, amount)
    assert inv.amount_allocated_pence == 0 and inv.paid_at is None


@pytest.mark.parametrize('change', ['debit', 'anticipated', 'unapproved', 'reversal', 'charge'])
def test_ineligible_posting_rejected(change):
    from sqlalchemy import select
    from app.models import LedgerEntry, LedgerDirection
    db, user, _, inv, pair = allocation_fixture()
    leg = db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id == pair))
    if change == 'debit': leg.direction = LedgerDirection.debit
    if change == 'anticipated': leg.is_anticipated = True
    if change == 'unapproved': leg.is_approved = False
    if change == 'reversal': inv.reversal_pair_id = pair
    if change == 'charge': inv.ledger_pair_id = pair
    db.commit()
    with pytest.raises(HTTPException, match='non-anticipated receipt'):
        allocate(db, user, inv, pair)
    assert inv.amount_allocated_pence == 0


def test_cross_matter_rejected_even_for_admin():
    db, user, _, inv, pair = allocation_fixture()
    other = add_case(db, fee_earner_user_id=user.id)
    inv.case_id = other.id
    db.commit()
    with pytest.raises(HTTPException, match="invoice's matter"):
        allocate(db, user, inv, pair)


@pytest.mark.parametrize('hidden', ['source', 'invoice'])
def test_cross_user_access_checked_on_both_matters(hidden):
    from app.models import UserRole
    from app.models.case_matter import CaseLockMode
    db, admin, source, inv, pair = allocation_fixture()
    user = add_user(db, role=UserRole.user, permission_category_id=admin.permission_category_id)
    target = add_case(db, fee_earner_user_id=admin.id)
    inv.case_id = target.id
    (source if hidden == 'source' else target).lock_mode = CaseLockMode.allow_list
    db.commit()
    with pytest.raises(HTTPException) as error:
        allocate(db, user, inv, pair)
    assert error.value.status_code == 403
    assert inv.amount_allocated_pence == 0


def test_lost_response_retry_returns_original_and_one_audit():
    from sqlalchemy import select, func
    from app.models import AuditEvent, CaseInvoiceAllocation
    db, user, _, inv, pair = allocation_fixture()
    key = uuid.uuid4()
    original = allocate(db, user, inv, pair, 10000, idempotency_key=key)
    db.commit()  # Server committed, client did not receive response.
    retry = allocate(db, user, inv, pair, 10000, idempotency_key=key)
    assert retry.id == original.id
    assert db.scalar(select(func.count()).select_from(CaseInvoiceAllocation)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'case.invoice.allocate')) == 1
    assert inv.amount_allocated_pence == 10000
    with pytest.raises(HTTPException) as error:
        allocate(db, user, inv, pair, 1, idempotency_key=key)
    assert error.value.status_code == 409


def test_audit_failure_rolls_back_all_financial_changes(monkeypatch):
    from sqlalchemy import select, func
    from app.models import CaseInvoiceAllocation
    import app.invoice_allocation_service as service
    db, user, _, inv, pair = allocation_fixture()
    def fail(*args, **kwargs): raise RuntimeError('injected audit failure')
    monkeypatch.setattr(service, 'log_event', fail)
    with pytest.raises(RuntimeError):
        allocate(db, user, inv, pair, 10000)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(CaseInvoiceAllocation)) == 0
    db.refresh(inv)
    assert inv.amount_allocated_pence == 0 and inv.paid_at is None


def test_inconsistent_historical_totals_fail_closed():
    db, user, _, inv, pair = allocation_fixture()
    inv.amount_allocated_pence = 100
    db.commit()
    with pytest.raises(HTTPException) as error:
        allocate(db, user, inv, pair)
    assert error.value.status_code == 409
    assert inv.amount_allocated_pence == 100


def test_allocated_invoice_cannot_be_voided():
    from app.invoice_service import void_case_invoice
    db, user, case, inv, pair = allocation_fixture()
    allocate(db, user, inv, pair)
    db.commit()
    with pytest.raises(HTTPException) as error:
        void_case_invoice(case.id, inv.id, user, db)
    assert error.value.status_code == 409
    db.refresh(inv)
    assert inv.status == 'approved' and inv.amount_allocated_pence == 6000


def test_commit_failure_does_not_mark_paid(monkeypatch):
    from sqlalchemy import event, select, func
    from app.models import CaseInvoiceAllocation
    db, user, _, inv, pair = allocation_fixture()
    key = uuid.uuid4()
    def fail_commit(session): raise RuntimeError('injected commit failure')
    event.listen(db, 'before_commit', fail_commit)
    allocate(db, user, inv, pair, 10000, idempotency_key=key)
    with pytest.raises(RuntimeError): db.commit()
    db.rollback()
    event.remove(db, 'before_commit', fail_commit)
    assert db.scalar(select(func.count()).select_from(CaseInvoiceAllocation)) == 0
    db.refresh(inv)
    assert inv.amount_allocated_pence == 0 and inv.paid_at is None
    allocate(db, user, inv, pair, 10000, idempotency_key=key)
    db.commit()
    assert inv.amount_allocated_pence == 10000


def test_retry_rechecks_revoked_matter_access():
    from app.models import UserRole, CaseLockMode
    db, admin, case, inv, pair = allocation_fixture()
    user = add_user(db, role=UserRole.user, permission_category_id=admin.permission_category_id)
    case.lock_mode = CaseLockMode.none
    db.commit()
    key = uuid.uuid4()
    allocate(db, user, inv, pair, idempotency_key=key)
    db.commit()
    case.lock_mode = CaseLockMode.allow_list
    db.commit()
    with pytest.raises(HTTPException) as error:
        allocate(db, user, inv, pair, idempotency_key=key)
    assert error.value.status_code == 403


def test_balanced_bill_payment_counts_credit_once():
    from app.models import LedgerAccount, LedgerAccountType, LedgerEntry, LedgerDirection
    db, user, case, inv, pair = allocation_fixture()
    from sqlalchemy import select
    account = db.scalar(select(LedgerAccount).where(LedgerAccount.case_id == case.id,
        LedgerAccount.account_type == LedgerAccountType.client))
    db.add(LedgerEntry(account_id=account.id, pair_id=pair, direction=LedgerDirection.debit,
        amount_pence=10000, description='Bill payment', is_approved=True, is_anticipated=False,
        posted_by_user_id=user.id))
    db.commit()
    allocate(db, user, inv, pair, 10000)
    other = new_invoice(db, case.id, user.id)
    with pytest.raises(HTTPException, match='unallocated value'):
        allocate(db, user, other, pair, 1)
