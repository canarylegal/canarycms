"""Quote compose produces docx with merge codes from native fee scale."""

import io
import re
import uuid
import zipfile
from datetime import datetime

import pytest
from sqlalchemy import select

from app.compose_quote import merge_compose_quote_docx_bytes
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
from app.schemas import ComposeQuoteIn, ComposeQuoteLineIn


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_compose_quote_produces_docx_with_table(db) -> None:
    case = db.execute(select(Case).limit(1)).scalar_one_or_none()
    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if case is None or user is None:
        pytest.skip("seed data required")

    now = datetime.utcnow()
    scale_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    scale = FeeScale(
        id=scale_id,
        name="Test scale",
        reference="test01",
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
        id=uuid.uuid4(),
        category_id=cat_id,
        name="Legal fee",
        line_kind=FeeScaleLineKind.item,
        amount_kind=FeeScaleAmountKind.fixed,
        default_amount_pence=92500,
        include_in_vat=True,
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    db.add(scale)
    db.add(cat)
    db.add(line)
    db.commit()

    body = ComposeQuoteIn(
        original_filename="Quote — Test.docx",
        folder="",
        fee_scale_id=scale_id,
        precedent_merge_all_clients=True,
        quote_lines=[
            ComposeQuoteLineIn(name="Legal fee", line_kind="item", amount_pence=92500, is_bold=False),
        ],
    )
    out, mime = merge_compose_quote_docx_bytes(db, case.id, body)
    assert "wordprocessingml" in mime
    xml = zipfile.ZipFile(io.BytesIO(out)).read("word/document.xml").decode()
    assert "Legal fee" in xml
    assert re.search(r"925\.00|£925\.00", xml)
    assert "QUOTE_01_LABEL" not in xml  # merge codes should be replaced

    db.delete(line)
    db.delete(cat)
    db.delete(scale)
    db.commit()
