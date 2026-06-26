"""Blank e-mail compose uses BLANK_EMAIL, not the letter scaffold."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.compose_merge import merge_compose_docx_bytes, resolve_blank_email_compose_body
from app.db import SessionLocal
from app.docx_util import extract_plain_text_from_docx_bytes
from app.models import Case, Precedent
from app.precedent_constants import BLANK_EMAIL_PRECEDENT_REFERENCE, BLANK_LETTER_PRECEDENT_REFERENCE
from app.schemas import ComposeOfficeDocumentIn


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_blank_email_compose_resolves_to_blank_email_precedent(db) -> None:
    blank_email = db.execute(
        select(Precedent).where(Precedent.reference == BLANK_EMAIL_PRECEDENT_REFERENCE)
    ).scalar_one_or_none()
    if blank_email is None:
        pytest.skip("BLANK_EMAIL precedent not seeded")

    body = ComposeOfficeDocumentIn(original_filename="Email draft.docx", folder="", precedent_id=None)
    resolved = resolve_blank_email_compose_body(db, body)
    assert resolved.precedent_id == blank_email.id


def test_blank_email_compose_body_is_not_letter_layout(db) -> None:
    case = db.execute(select(Case).limit(1)).scalar_one_or_none()
    blank_email = db.execute(
        select(Precedent).where(Precedent.reference == BLANK_EMAIL_PRECEDENT_REFERENCE)
    ).scalar_one_or_none()
    blank_letter = db.execute(
        select(Precedent).where(Precedent.reference == BLANK_LETTER_PRECEDENT_REFERENCE)
    ).scalar_one_or_none()
    if case is None or blank_email is None or blank_letter is None:
        pytest.skip("seed data required")

    body = ComposeOfficeDocumentIn(
        original_filename="Email draft.docx",
        folder="",
        precedent_id=None,
        compose_office_role=None,
    )
    body = resolve_blank_email_compose_body(db, body)
    out, _mime = merge_compose_docx_bytes(db, case.id, body, require_precedent_kind=blank_email.kind)
    text = extract_plain_text_from_docx_bytes(out)

    letter_out, _ = merge_compose_docx_bytes(
        db,
        case.id,
        ComposeOfficeDocumentIn(
            original_filename="Letter — test.docx",
            folder="",
            precedent_id=None,
            compose_office_role="letter",
        ),
    )
    letter_text = extract_plain_text_from_docx_bytes(letter_out)

    assert "Re:" in letter_text
    assert "Re:" not in text
    assert "[ORG_AND_ADDRESS_BLOCK]" not in text
