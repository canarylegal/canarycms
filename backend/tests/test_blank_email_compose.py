"""Blank e-mail compose uses BLANK_EMAIL, not the letter scaffold."""

from __future__ import annotations

from tests.document_fixture_helpers import document_compose_fixture

from app.compose_merge import merge_compose_docx_bytes, resolve_blank_email_compose_body
from app.docx_util import extract_plain_text_from_docx_bytes
from app.precedent_constants import BLANK_EMAIL_PRECEDENT_REFERENCE
from app.schemas import ComposeOfficeDocumentIn


def test_blank_email_compose_resolves_to_blank_email_precedent(db, document_compose_fixture) -> None:
    blank_email = document_compose_fixture.precedents[BLANK_EMAIL_PRECEDENT_REFERENCE]

    body = ComposeOfficeDocumentIn(original_filename="Email draft.docx", folder="", precedent_id=None)
    resolved = resolve_blank_email_compose_body(db, body)
    assert resolved.precedent_id == blank_email.id


def test_blank_email_merges_without_contact(db, document_compose_fixture) -> None:
    """Matter-level codes must resolve even when no recipient contact is selected."""
    case = document_compose_fixture.case
    blank_email = document_compose_fixture.precedents[BLANK_EMAIL_PRECEDENT_REFERENCE]

    body = ComposeOfficeDocumentIn(
        original_filename="Email draft.docx",
        folder="",
        precedent_id=blank_email.id,
        case_contact_id=None,
        global_contact_id=None,
        precedent_merge_all_clients=False,
    )
    out, _mime = merge_compose_docx_bytes(db, case.id, body, require_precedent_kind=blank_email.kind)
    text = extract_plain_text_from_docx_bytes(out)
    assert "[CASE_REF]" not in text
    assert "[FEE_EARNER]" not in text
    assert "[DATE]" not in text
    assert case.case_number in text


def test_blank_email_compose_body_is_not_letter_layout(db, document_compose_fixture) -> None:
    case = document_compose_fixture.case
    blank_email = document_compose_fixture.precedents[BLANK_EMAIL_PRECEDENT_REFERENCE]

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
