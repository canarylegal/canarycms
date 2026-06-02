"""Compose quote line resolution must keep VAT from fee scale calculation."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.compose_quote import _computed_from_compose_lines, resolve_compose_quote_lines
from app.db import SessionLocal
from app.models import (
    Case,
    FeeScale,
    FeeScaleAmountKind,
    FeeScaleCategory,
    FeeScaleLine,
    FeeScaleLineKind,
    User,
)
from app.schemas import ComposeQuoteIn, ComposeQuoteLineIn, QuoteDraftCategoryIn, QuoteDraftLineIn


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_computed_from_compose_lines_preserves_vat_pence() -> None:
    lines = [
        ComposeQuoteLineIn(
            name="Legal fee",
            line_kind="item",
            amount_pence=100_000,
            vat_pence=20_000,
            is_bold=False,
        ),
    ]
    out = _computed_from_compose_lines(lines)
    assert len(out) == 1
    assert out[0].vat_pence == 20_000


def test_resolve_prefers_draft_over_stale_quote_lines(db) -> None:
    case = db.execute(select(Case).limit(1)).scalar_one_or_none()
    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if case is None or user is None:
        pytest.skip("seed data required")

    now = datetime.utcnow()
    scale_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    line_id = uuid.uuid4()
    scale = FeeScale(
        id=scale_id,
        name="VAT resolve test",
        reference=f"vatres{uuid.uuid4().hex[:8]}",
        vat_rate_bps=2000,
        owner_id=user.id,
        created_at=now,
        updated_at=now,
    )
    cat = FeeScaleCategory(
        id=cat_id,
        fee_scale_id=scale_id,
        name="Fees",
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    line = FeeScaleLine(
        id=line_id,
        category_id=cat_id,
        name="Legal fee",
        line_kind=FeeScaleLineKind.item,
        amount_kind=FeeScaleAmountKind.fixed,
        default_amount_pence=100_000,
        vat_treatment="plus_vat",
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    db.add(scale)
    db.add(cat)
    db.add(line)
    db.commit()

    draft = [
        QuoteDraftCategoryIn(
            key="c1",
            category_id=str(cat_id),
            name="Fees",
            sort_order=0,
            lines=[
                QuoteDraftLineIn(
                    key="l1",
                    line_id=str(line_id),
                    name="Legal fee",
                    line_kind="item",
                    amount_kind="fixed",
                    amount_pence=100_000,
                    vat_treatment="plus_vat",
                    sort_order=0,
                ),
            ],
        ),
    ]
    body = ComposeQuoteIn(
        original_filename="Quote.docx",
        fee_scale_id=scale_id,
        draft=draft,
        quote_lines=[
            ComposeQuoteLineIn(
                name="Legal fee",
                line_kind="item",
                amount_pence=100_000,
                vat_pence=None,
                is_bold=False,
            ),
        ],
    )
    computed = resolve_compose_quote_lines(db, case.id, body)
    assert any(ln.vat_pence == 20_000 for ln in computed)

    db.delete(line)
    db.delete(cat)
    db.delete(scale)
    db.commit()
