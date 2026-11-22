"""Synthetic document assets: no operator downloads or pre-seeded firm templates."""
import io
import uuid
from types import SimpleNamespace

import pytest
from docx import Document
from docx.shared import Inches
from PIL import Image
from sqlalchemy import select

from app import compose_merge, compose_quote, file_storage, global_precedent_loader
from app.models import File, FileCategory, FirmSettings, LetterheadStyle, Precedent, PrecedentKind
from app.precedent_constants import BLANK_EMAIL_PRECEDENT_REFERENCE, BLANK_LETTER_PRECEDENT_REFERENCE, QUOTE_TEMPLATE_PRECEDENT_REFERENCE
from tests.ledger_test_helpers import add_case, add_user


def docx_bytes(doc):
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


def quote_document():
    doc = Document()
    doc.add_paragraph('Synthetic quote [CASE_REF] [DATE] [MATTER_DESCRIPTION]')
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = 'Description'
    table.rows[0].cells[1].text = 'Amount'
    for i in range(1, 16):
        row = table.add_row()
        row.cells[0].text = f'[QUOTE_{i:02d}_LABEL]'
        row.cells[1].text = f'[QUOTE_{i:02d}_AMOUNT]'
    return doc


@pytest.fixture
def document_compose_fixture(db, tmp_path, monkeypatch):
    user = add_user(db)
    case = add_case(db, fee_earner_user_id=user.id)
    for module in (compose_merge, compose_quote, file_storage, global_precedent_loader):
        monkeypatch.setattr(module, 'FILES_ROOT', tmp_path)
    # Isolate reserved-name selection from any other test's seed data. Rollback restores it.
    refs = [BLANK_EMAIL_PRECEDENT_REFERENCE, BLANK_LETTER_PRECEDENT_REFERENCE, QUOTE_TEMPLATE_PRECEDENT_REFERENCE]
    for row in db.scalars(select(Precedent).where(Precedent.reference.in_(refs))):
        row.reference = 'fixture-shadow-' + uuid.uuid4().hex
    db.flush()

    def save_asset(doc, category):
        raw = docx_bytes(doc)
        name = uuid.uuid4().hex + '.docx'
        (tmp_path / name).write_bytes(raw)
        row = File(owner_id=user.id, category=category, storage_path=name, original_filename=name,
                   mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                   folder_path='', version=1, size_bytes=len(raw))
        db.add(row)
        db.flush()
        return row

    precedents = {}
    for reference, kind, paragraphs in (
        (BLANK_EMAIL_PRECEDENT_REFERENCE, PrecedentKind.email, ['Email reference [CASE_REF]', '[FEE_EARNER]', '[DATE]', '[PRECEDENT_BODY]']),
        (BLANK_LETTER_PRECEDENT_REFERENCE, PrecedentKind.letter, ['[ORG_AND_ADDRESS_BLOCK]', '[DATE]', 'Re: [CASE_REF]', '[PRECEDENT_BODY]']),
    ):
        doc = Document()
        for value in paragraphs:
            doc.add_paragraph(value)
        asset = save_asset(doc, FileCategory.precedent)
        row = Precedent(name='Synthetic ' + reference, reference=reference, kind=kind, file_id=asset.id)
        db.add(row)
        db.flush()
        precedents[reference] = row

    letterhead = quote_document()
    picture = io.BytesIO()
    Image.new('RGB', (8, 8), (20, 80, 160)).save(picture, format='PNG')
    picture.seek(0)
    header = letterhead.sections[0].header.paragraphs[0]
    header.add_run('Synthetic letterhead ')
    header.add_run().add_picture(picture, width=Inches(0.2))
    asset = save_asset(letterhead, FileCategory.firm_letterhead)
    firm = db.get(FirmSettings, 1)
    if firm is None:
        firm = FirmSettings(id=1, trading_name="Synthetic firm")
        db.add(firm)
    firm.letterhead_style = LetterheadStyle.preprinted
    firm.quote_letterhead_style = LetterheadStyle.digital
    firm.quote_letterhead_file_id = asset.id
    db.flush()
    try:
        yield SimpleNamespace(case=case, firm=firm, precedents=precedents)
    finally:
        db.rollback()
