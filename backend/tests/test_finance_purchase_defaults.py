"""Default finance template for residential conveyancing purchase."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.finance_service import (
    FUNDS_RECEIVED_CATEGORY_NAME,
    PURCHASE_COSTS_CATEGORY_NAME,
    PURCHASE_PRICE_ITEM_NAME,
    _ensure_default_finance_template_categories,
    _is_residential_conveyancing_purchase_sub_type,
)
from app.models import FinanceCategoryTemplate, FinanceItemTemplate, MatterHeadType, MatterSubType


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def test_residential_purchase_default_finance_template(db) -> None:
    now = datetime.now(timezone.utc)
    head = MatterHeadType(id=uuid.uuid4(), name="Conveyancing, Residential", created_at=now, updated_at=now)
    sub = MatterSubType(
        id=uuid.uuid4(),
        head_type_id=head.id,
        name="Purchase",
        prefix="Purchase of",
        created_at=now,
        updated_at=now,
    )
    db.add(head)
    db.add(sub)
    db.flush()

    assert _is_residential_conveyancing_purchase_sub_type(sub.id, db)

    _ensure_default_finance_template_categories(sub.id, db)

    cats = db.execute(
        select(FinanceCategoryTemplate)
        .where(FinanceCategoryTemplate.matter_sub_type_id == sub.id)
        .order_by(FinanceCategoryTemplate.sort_order)
    ).scalars().all()
    assert len(cats) == 2
    assert cats[0].name == PURCHASE_COSTS_CATEGORY_NAME
    assert not cats[0].credit_only
    assert cats[1].name == FUNDS_RECEIVED_CATEGORY_NAME
    assert cats[1].credit_only

    items = db.execute(
        select(FinanceItemTemplate).where(FinanceItemTemplate.category_id == cats[0].id)
    ).scalars().all()
    assert len(items) == 1
    assert items[0].name == PURCHASE_PRICE_ITEM_NAME
    assert items[0].direction == "debit"
