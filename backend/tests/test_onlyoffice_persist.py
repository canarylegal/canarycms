"""ONLYOFFICE downloadAs persist helper."""

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models import File as DbFile
from app.routers.onlyoffice import fix_pdf_form_need_appearances, persist_onlyoffice_browser_url_to_file


def test_fix_pdf_form_need_appearances_sets_flag() -> None:
    pytest.importorskip("pikepdf")
    import pikepdf

    pdf = pikepdf.new()
    pdf.Root.AcroForm = pikepdf.Dictionary(
        Fields=pikepdf.Array([]),
        NeedAppearances=False,
    )
    buf = BytesIO()
    pdf.save(buf)
    raw = buf.getvalue()
    fixed = fix_pdf_form_need_appearances(raw)
    with pikepdf.open(BytesIO(fixed)) as opened:
        assert bool(opened.Root.AcroForm.get("/NeedAppearances")) is True


@pytest.mark.asyncio
async def test_persist_rejects_non_pdf_for_pdf_file(tmp_path, monkeypatch) -> None:
    row = DbFile(
        id=uuid.uuid4(),
        original_filename="test.pdf",
        storage_path="cases/x/test.pdf",
        version=1,
    )
    db = MagicMock()
    monkeypatch.setattr("app.routers.onlyoffice.FILES_ROOT", tmp_path)
    monkeypatch.setattr("app.routers.onlyoffice.ensure_files_root", lambda: None)

    with patch(
        "app.routers.onlyoffice._internal_fetch_url_from_browser",
        return_value="http://onlyoffice/cache/files/x",
    ):
        with patch("httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client_cls.return_value.__aenter__.return_value = client
            resp = MagicMock()
            resp.content = b"not a pdf"
            resp.raise_for_status = MagicMock()
            client.get.return_value = resp

            with pytest.raises(HTTPException) as exc:
                await persist_onlyoffice_browser_url_to_file(
                    db,
                    row,
                    browser_url="https://dev.example/office-ds/cache/files/x",
                    case_id=uuid.uuid4(),
                    precedent_id=None,
                )
    assert exc.value.status_code == 400
