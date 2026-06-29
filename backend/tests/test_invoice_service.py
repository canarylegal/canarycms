"""Tests for case invoice create, approve, and void ledger integration."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.invoice_service import (
    INV_APPROVED,
    INV_PENDING,
    INV_VOIDED,
    approve_case_invoice,
    create_case_invoice,
    list_case_invoices,
    void_case_invoice,
)
from app.ledger_service import get_ledger, post_transaction
from app.models import FirmSettings
from app.schemas import CaseInvoiceCreate, CaseInvoiceLineCreate, LedgerPostCreate

from tests.ledger_test_helpers import add_case, add_user, ledger_test_session


def _invoice_payload(*, credit_user_id, fee_pence: int = 10_000, vat_pence: int = 2_000) -> CaseInvoiceCreate:
    return CaseInvoiceCreate(
        credit_user_id=credit_user_id,
        lines=[
            CaseInvoiceLineCreate(
                line_type="fee",
                description="Professional fees",
                amount_pence=fee_pence,
                tax_pence=vat_pence,
            ),
        ],
    )


def test_create_invoice_posts_pending_office_debit_without_affecting_balance() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    inv = create_case_invoice(case.id, _invoice_payload(credit_user_id=admin.id), admin, db)
    db.commit()

    assert inv.status == INV_PENDING
    assert inv.total_pence == 12_000

    ledger = get_ledger(case.id, db)
    assert ledger.office.balance_pence == 0

    rows = list_case_invoices(case.id, db).invoices
    assert len(rows) == 1
    assert rows[0].total_pence == 12_000
    assert sum(ln.amount_pence + ln.tax_pence for ln in rows[0].lines) == 12_000


def test_approve_invoice_applies_office_debit() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    inv = create_case_invoice(case.id, _invoice_payload(credit_user_id=admin.id), admin, db)
    approve_case_invoice(case.id, inv.id, admin, db)
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.office.balance_pence == -12_000

    rows = list_case_invoices(case.id, db).invoices
    assert rows[0].status == INV_APPROVED


def test_approve_invoice_saves_document_file() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)
    db.add(FirmSettings(id=1, trading_name="Test Firm"))
    db.commit()

    inv = create_case_invoice(case.id, _invoice_payload(credit_user_id=admin.id), admin, db)
    approve_case_invoice(case.id, inv.id, admin, db)
    db.commit()

    row = list_case_invoices(case.id, db).invoices[0]
    assert row.document_file_id is not None


def test_void_pending_invoice_removes_ledger_posting() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    inv = create_case_invoice(case.id, _invoice_payload(credit_user_id=admin.id), admin, db)
    void_case_invoice(case.id, inv.id, admin, db)
    db.commit()

    ledger = get_ledger(case.id, db)
    assert ledger.office.balance_pence == 0
    assert list_case_invoices(case.id, db).invoices[0].status == INV_VOIDED


def test_void_approved_invoice_reverses_office_debit_when_balance_allows() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    inv = create_case_invoice(
        case.id,
        _invoice_payload(credit_user_id=admin.id, fee_pence=5_000, vat_pence=0),
        admin,
        db,
    )
    approve_case_invoice(case.id, inv.id, admin, db)
    db.commit()

    assert get_ledger(case.id, db).office.balance_pence == -5_000

    void_case_invoice(case.id, inv.id, admin, db)
    db.commit()

    assert get_ledger(case.id, db).office.balance_pence == 0
    assert list_case_invoices(case.id, db).invoices[0].status == INV_VOIDED


def test_void_approved_invoice_blocked_when_reversal_would_over_credit_office() -> None:
    db = ledger_test_session()
    admin = add_user(db)
    case = add_case(db, fee_earner_user_id=admin.id)

    inv = create_case_invoice(
        case.id,
        _invoice_payload(credit_user_id=admin.id, fee_pence=5_000, vat_pence=0),
        admin,
        db,
    )
    approve_case_invoice(case.id, inv.id, admin, db)
    db.commit()

    post_transaction(
        case.id,
        LedgerPostCreate(
            description="Partial payment",
            amount_pence=2_000,
            office_direction="credit",
        ),
        admin,
        db,
    )
    db.commit()
    assert get_ledger(case.id, db).office.balance_pence == -3_000

    with pytest.raises(HTTPException) as exc:
        void_case_invoice(case.id, inv.id, admin, db)
    assert exc.value.status_code == 422
    assert "office account balance" in str(exc.value.detail).lower()

    db.rollback()
    assert list_case_invoices(case.id, db).invoices[0].status == INV_APPROVED
