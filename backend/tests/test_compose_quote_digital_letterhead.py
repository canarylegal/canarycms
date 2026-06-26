"""Digital quote letterhead overlay on fee-scale quote compose."""

import io
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.compose_merge import apply_quote_digital_letterhead_from_settings
from app.compose_quote import merge_compose_quote_docx_bytes
from app.db import SessionLocal
from app.models import Case, FirmSettings, LetterheadStyle
from app.schemas import ComposeQuoteIn, ComposeQuoteLineIn


def _has_header_media(docx_bytes: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return any(n.startswith("word/media/") for n in z.namelist())


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_apply_quote_digital_letterhead_skips_when_preprinted() -> None:
    firm = SimpleNamespace(
        quote_letterhead_style=LetterheadStyle.preprinted,
        quote_letterhead_file_id=None,
    )
    out, lh_bytes = apply_quote_digital_letterhead_from_settings(None, firm_row=firm, src_bytes=b"plain")  # type: ignore[arg-type]
    assert out == b"plain"
    assert lh_bytes is None


def test_compose_quote_applies_digital_letterhead_when_configured(db) -> None:
    case = db.execute(select(Case).limit(1)).scalar_one_or_none()
    firm = db.get(FirmSettings, 1)
    if case is None or firm is None:
        pytest.skip("seed data required")
    if firm.quote_letterhead_style != LetterheadStyle.digital or not firm.quote_letterhead_file_id:
        pytest.skip("quote digital letterhead not configured in firm settings")

    body = ComposeQuoteIn(
        original_filename="Quote — Test.docx",
        folder="",
        quote_lines=[
            ComposeQuoteLineIn(name="Fee", line_kind="item", amount_pence=10000, is_bold=False),
        ],
    )
    out, _mime = merge_compose_quote_docx_bytes(db, case.id, body)
    assert _has_header_media(out), "quote compose should copy letterhead header media when digital mode is on"
