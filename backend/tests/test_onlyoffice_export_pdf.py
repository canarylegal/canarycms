"""ONLYOFFICE Save as PDF (new case file)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models import File as DbFile
from app.routers.onlyoffice import allocate_pdf_export_filename, create_case_file_from_onlyoffice_pdf_export


def test_allocate_pdf_export_filename_dedupes() -> None:
    db = MagicMock()
    case_id = uuid.uuid4()
    existing = {("Letter.pdf",), ("Letter (2).pdf",)}
    db.execute.return_value.all.return_value = existing
    name = allocate_pdf_export_filename(
        db,
        case_id=case_id,
        folder_path="Docs",
        preferred="Letter.pdf",
    )
    assert name == "Letter (3).pdf"


@pytest.mark.asyncio
async def test_export_pdf_rejects_pdf_source() -> None:
    source = DbFile(
        id=uuid.uuid4(),
        case_id=uuid.uuid4(),
        original_filename="already.pdf",
        folder_path="",
        version=1,
    )
    db = MagicMock()
    user = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await create_case_file_from_onlyoffice_pdf_export(
            db,
            source,
            browser_url="https://dev.example/office-ds/cache/files/x",
            case_id=source.case_id,
            user=user,
        )
    assert exc.value.status_code == 400
