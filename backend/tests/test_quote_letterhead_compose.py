"""Firm letterhead on letter compose (including blank-letter path)."""

import io
import zipfile

import pytest
from sqlalchemy import select

from app.compose_merge import merge_compose_docx_bytes
from app.db import SessionLocal
from app.models import Case, Precedent, PrecedentKind
from app.schemas import ComposeOfficeDocumentIn


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


def test_letter_blank_compose_applies_firm_letterhead(db) -> None:
    case = db.execute(select(Case).limit(1)).scalar_one_or_none()
    blank = db.execute(
        select(Precedent).where(Precedent.kind == PrecedentKind.letter).limit(1)
    ).scalar_one_or_none()
    if case is None or blank is None:
        pytest.skip("seed data required")

    body = ComposeOfficeDocumentIn(
        original_filename="Letter — Quote.docx",
        folder="",
        precedent_id=None,
        compose_office_role="letter",
    )
    out, _mime = merge_compose_docx_bytes(db, case.id, body)
    assert _has_header_media(out), "letter blank compose should include firm letterhead media when digital mode is configured"
