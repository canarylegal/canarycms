"""Allocation correction outcomes, durable retries and explicit historical diagnostics."""
import uuid
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from app import invoice_allocation_corrections as service
from app.invoice_allocation_integrity import allocation_total, invoice_consistency
from app.models import (AuditEvent, CaseInvoiceAllocation, InvoiceAllocationReversal, LedgerEntry,
                        CaseLockMode, UserRole)
from app.schemas.bank import InvoiceAllocationReversalIn
from tests.test_invoice_allocation import allocation_fixture, allocate, new_invoice
from tests.ledger_test_helpers import add_user, add_case


def payload(reason='Correct allocation'):
    return InvoiceAllocationReversalIn(idempotency_key=uuid.uuid4(), reason=reason)


def reverse(db, user, invoice, allocation, request=None):
    return service.reverse_allocation(db, invoice_id=invoice.id, allocation_id=allocation.id,
        actor=user, payload=request or payload())


def fixture(db=None):
    db, user, matter, invoice, pair = allocation_fixture(db)
    original = allocate(db, user, invoice, pair, 10000, idempotency_key=uuid.uuid4())
    db.commit()
    return db, user, matter, invoice, pair, original


def test_reversal_preserves_original_releases_capacity_and_reopens_invoice():
    db, user, matter, invoice, pair, original = fixture()
    original_fields = (original.amount_pence, original.allocated_at, original.allocated_by_user_id, original.notes)
    request = payload()
    result = reverse(db, user, invoice, original, request); db.commit()
    assert invoice.amount_allocated_pence == 0 and invoice.paid_at is None
    assert allocation_total(db, pair_id=pair) == 0
    assert (original.amount_pence, original.allocated_at, original.allocated_by_user_id, original.notes) == original_fields
    assert reverse(db, user, invoice, original, request).id == result.id
    assert db.scalar(select(func.count()).select_from(InvoiceAllocationReversal)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'case.invoice.allocation.reverse')) == 1
    # Retrying the original allocation cannot silently reapply a corrected payment.
    assert allocate(db, user, invoice, pair, 10000, idempotency_key=original.idempotency_key).id == original.id
    assert invoice.amount_allocated_pence == 0
    other = new_invoice(db, matter.id, user.id)
    allocate(db, user, other, pair, 10000); db.commit()
    assert other.paid_at and other.amount_allocated_pence == 10000
    assert service.check_invoice_allocations(db, invoice_id=invoice.id, actor=user)['consistent']
    assert service.check_invoice_allocations(db, invoice_id=other.id, actor=user)['consistent']


def test_partial_payment_correction_preserves_other_allocations():
    db, user, _, invoice, pair = allocation_fixture()
    first = allocate(db, user, invoice, pair, 4000)
    second = allocate(db, user, invoice, pair, 6000)
    db.commit()
    reverse(db, user, invoice, first); db.commit()
    assert invoice.amount_allocated_pence == 6000 and invoice.paid_at is None
    assert allocation_total(db, pair_id=pair) == 6000
    allocate(db, user, invoice, pair, 3000); db.commit()
    assert invoice.amount_allocated_pence == 9000 and invoice.paid_at is None
    assert db.get(CaseInvoiceAllocation, second.id).amount_pence == 6000


@pytest.mark.parametrize('change', ['reason', 'key', 'allocation'])
def test_corrections_cannot_be_reused_for_other_details_or_reversed_twice(change):
    db, user, _, inv, _, original = fixture()
    request = payload()
    reverse(db, user, inv, original, request); db.commit()
    if change == 'reason': request = request.model_copy(update={'reason': 'Different reason'})
    if change == 'key': request = payload()
    if change == 'allocation':
        original = allocate(db, user, inv, original.ledger_pair_id, 1000); db.commit()
    with pytest.raises(HTTPException) as error: reverse(db, user, inv, original, request)
    assert error.value.status_code == 409


@pytest.mark.parametrize('failure', ['audit', 'flush', 'commit'])
def test_failure_rolls_back_reversal_totals_paid_status_and_audit(failure, monkeypatch):
    db, user, _, invoice, _, original = fixture()
    paid_at = invoice.paid_at
    request = payload()
    def fail(*args, **kwargs): raise RuntimeError('Injected persistence failure')
    with monkeypatch.context() as patch:
        if failure == 'audit': patch.setattr(service, 'log_event', fail)
        if failure == 'flush':
            def fail_flush(session, *_):
                if any(isinstance(row, InvoiceAllocationReversal) for row in session.new): fail()
            event.listen(db, 'before_flush', fail_flush)
        if failure == 'commit': event.listen(db, 'before_commit', fail)
        with pytest.raises(RuntimeError):
            reverse(db, user, invoice, original, request)
            db.commit()
        db.rollback()
        if failure == 'flush': event.remove(db, 'before_flush', fail_flush)
        if failure == 'commit': event.remove(db, 'before_commit', fail)
    assert invoice.amount_allocated_pence == 10000 and invoice.paid_at == paid_at
    assert db.scalar(select(func.count()).select_from(InvoiceAllocationReversal)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'case.invoice.allocation.reverse')) == 0
    reverse(db, user, invoice, original, request); db.commit()
    assert invoice.amount_allocated_pence == 0 and invoice.paid_at is None


@pytest.mark.parametrize('denial', ['invoice_access', 'source_access', 'permission', 'inactive'])
def test_retry_and_consistency_recheck_permissions(denial):
    db, admin, matter, invoice, pair, original = fixture()
    user = add_user(db, role=UserRole.user, permission_category_id=admin.permission_category_id)
    request = payload()
    reverse(db, user, invoice, original, request); db.commit()
    if denial == 'invoice_access': matter.lock_mode = CaseLockMode.allow_list
    if denial == 'source_access':
        target = add_case(db, fee_earner_user_id=admin.id)
        invoice.case_id = target.id
        matter.lock_mode = CaseLockMode.allow_list
    if denial == 'permission': user.permission_category_id = None
    if denial == 'inactive': user.is_active = False
    db.commit()
    for action in ('retry', 'check'):
        with pytest.raises(HTTPException) as error:
            if action == 'retry': reverse(db, user, invoice, original, request)
            else: service.check_invoice_allocations(db, invoice_id=invoice.id, actor=user)
        assert error.value.status_code == 403


def test_reversal_must_belong_to_requested_invoice_and_reason_is_required():
    db, user, matter, invoice, _, original = fixture()
    other = new_invoice(db, matter.id, user.id); db.commit()
    with pytest.raises(HTTPException) as error: reverse(db, user, other, original)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error: reverse(db, user, invoice, original, payload('   '))
    assert error.value.status_code == 400


@pytest.mark.parametrize('broken,code', [('cache','cached_total_mismatch'), ('paid','paid_status_mismatch'),
    ('invoice_capacity','invoice_overallocated'), ('receipt_capacity','receipt_overallocated'),
    ('source','invalid_receipt'), ('status','allocated_invoice_not_approved'), ('case','cross_matter_receipt')])
def test_consistency_reports_historical_discrepancies_without_repairs(broken, code):
    db, user, _, invoice, pair, original = fixture()
    if broken == 'cache': invoice.amount_allocated_pence = 123
    if broken == 'paid': invoice.paid_at = None
    if broken == 'invoice_capacity': invoice.total_pence = 5000
    if broken == 'receipt_capacity': db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id == pair)).amount_pence = 5000
    if broken == 'source': db.scalar(select(LedgerEntry).where(LedgerEntry.pair_id == pair)).is_approved = False
    if broken == 'status': invoice.status = 'voided'
    if broken == 'case': invoice.case_id = add_case(db, fee_earner_user_id=user.id).id
    db.commit()
    before = (invoice.amount_allocated_pence, invoice.paid_at, invoice.status)
    report = service.check_invoice_allocations(db, invoice_id=invoice.id, actor=user)
    assert not report['consistent'] and code in {i['code'] for i in report['issues']}
    assert (invoice.amount_allocated_pence, invoice.paid_at, invoice.status) == before
    with pytest.raises(HTTPException): reverse(db, user, invoice, original)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(InvoiceAllocationReversal)) == 0


def test_corrected_allocation_no_longer_blocks_ledger_reversal_or_invoice_void():
    from app.ledger_operations import reverse_posting
    from app.schemas.ledger import LedgerReversalCreate
    from app.invoice_service import void_case_invoice
    db, user, matter, invoice, pair, original = fixture()
    request = payload()
    reverse(db, user, invoice, original, request); db.commit()
    reverse_posting(db, case_id=matter.id, pair_id=pair,
        payload=LedgerReversalCreate(idempotency_key=uuid.uuid4(), reason='Correct receipt after unallocation'), user=user)
    db.commit()
    from app.ledger_service import post_transaction
    from app.schemas import LedgerPostCreate
    invoice.ledger_pair_id = post_transaction(matter.id, LedgerPostCreate(description='Invoice charge',
        amount_pence=10000, office_direction='debit'), user, db).pair_id
    db.commit()
    void_case_invoice(matter.id, invoice.id, user, db); db.commit()
    assert invoice.status == 'voided'
    assert reverse(db, user, invoice, original, request)
    assert invoice_consistency(db, invoice)['consistent']


def test_inconsistent_other_invoice_sharing_receipt_is_reported_and_blocks_correction():
    db, user, matter, inv, pair = allocation_fixture()
    original = allocate(db, user, inv, pair, 5000)
    other = new_invoice(db, matter.id, user.id)
    allocate(db, user, other, pair, 5000); db.commit()
    other.status = 'voided'; db.commit()
    result = service.check_invoice_allocations(db, invoice_id=inv.id, actor=user)
    assert 'receipt_allocations_inconsistent' in {i['code'] for i in result['issues']}
    with pytest.raises(HTTPException): reverse(db, user, inv, original)
    assert inv.amount_allocated_pence == 5000


def test_correction_updates_outstanding_amount_in_aged_debt():
    from app.reports_service import report_aged_debt
    from app.ledger_service import post_transaction
    from app.schemas import LedgerPostCreate
    db, user, matter, inv, _, original = fixture()
    post_transaction(matter.id, LedgerPostCreate(description='Outstanding office charges',
        amount_pence=20000, office_direction='debit'), user, db)
    db.commit()
    rows, _ = report_aged_debt([user.id], db)
    assert inv.id not in {r.invoice_id for r in rows}
    reverse(db, user, inv, original); db.commit()
    rows, _ = report_aged_debt([user.id], db)
    assert next(r.invoice_total_pence for r in rows if r.invoice_id == inv.id) == 10000
