"""Finance item plus-VAT treatment."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.billing_service import update_default_vat_percent
from app.db import SessionLocal
from app.finance_service import (
    _billing_vat_rate_bps,
    _sync_item_vat_from_treatment,
    update_finance_item,
)
from app.models import Case, FinanceCategory, FinanceItem, FeeScaleVatTreatment
from app.schemas import FinanceItemUpdate


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_sync_item_vat_from_treatment_computes_plus_vat() -> None:
    item = FinanceItem(
        id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        name="Custom fee",
        direction="debit",
        amount_pence=10_000,
        vat_treatment=FeeScaleVatTreatment.plus_vat,
        sort_order=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    _sync_item_vat_from_treatment(item, 2000)
    assert item.vat_pence == 2000


def test_billing_vat_rate_bps_uses_admin_settings(db) -> None:
    update_default_vat_percent(db, Decimal("19.5"))
    assert _billing_vat_rate_bps(db) == 1950
    db.rollback()


def test_update_finance_item_applies_plus_vat(db) -> None:
    case = db.execute(select(Case).limit(1)).scalar_one()
    cat = FinanceCategory(
        id=uuid.uuid4(),
        case_id=case.id,
        name="Manual fees test",
        sort_order=99,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(cat)
    db.flush()
    item = FinanceItem(
        id=uuid.uuid4(),
        category_id=cat.id,
        name="Extra work",
        direction="debit",
        amount_pence=5_000,
        sort_order=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.flush()

    out = update_finance_item(
        case.id,
        item.id,
        FinanceItemUpdate(vat_treatment="plus_vat"),
        db,
    )
    assert out.vat_treatment == "plus_vat"
    assert out.vat_pence == 1000

    db.rollback()
