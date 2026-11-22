"""Firm letterhead on blank-letter compose, using only synthetic settings/files."""
import io
import uuid
import zipfile

import pytest
from app import compose_merge, file_storage
from app.models import File, FileCategory, FirmSettings, LetterheadStyle
from app.schemas import ComposeOfficeDocumentIn
from tests.ledger_test_helpers import ledger_test_session, add_user, add_case
from tests.test_letterhead_media_merge import _letterhead_with_header_image


@pytest.mark.parametrize('style', [LetterheadStyle.digital, LetterheadStyle.preprinted])
def test_letter_blank_compose_applies_firm_letterhead(tmp_path, monkeypatch, style) -> None:
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setattr(compose_merge, 'FILES_ROOT', tmp_path)
    with ledger_test_session() as db:
        actor = add_user(db)
        case = add_case(db, fee_earner_user_id=actor.id)
        letterhead = _letterhead_with_header_image()
        path = 'synthetic-letterhead.docx'
        (tmp_path / path).write_bytes(letterhead)
        row = File(id=uuid.uuid4(), owner_id=actor.id, category=FileCategory.firm_letterhead,
                   storage_path=path, original_filename=path,
                   mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                   size_bytes=len(letterhead))
        db.add(row)
        db.flush()
        db.add(FirmSettings(id=1, letterhead_style=style, letterhead_file_id=row.id))
        db.flush()
        body = ComposeOfficeDocumentIn(original_filename='Letter — Test.docx', folder='',
                                       precedent_id=None, compose_office_role='letter')
        out, _mime = compose_merge.merge_compose_docx_bytes(db, case.id, body)
        with zipfile.ZipFile(io.BytesIO(out)) as archive:
            has_media = any(name.startswith('word/media/') for name in archive.namelist())
        assert has_media == (style == LetterheadStyle.digital)
