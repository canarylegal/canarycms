"""Feature flag helpers."""

from unittest.mock import patch

import pytest

from app.feature_flags import (
    onlyoffice_editor_customization,
    onlyoffice_pdf_editor_types,
    open_pdf_in_onlyoffice,
)
from app.routers.files import _onlyoffice_types_for_file


def test_open_pdf_in_onlyoffice_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CANARY_OPEN_PDF_IN_ONLYOFFICE", raising=False)
    assert open_pdf_in_onlyoffice() is False
    assert _onlyoffice_types_for_file("report.pdf") is None


def test_open_pdf_in_onlyoffice_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_OPEN_PDF_IN_ONLYOFFICE", "1")
    assert open_pdf_in_onlyoffice() is True
    with patch("app.feature_flags.onlyoffice_ds_major", return_value=9):
        assert onlyoffice_pdf_editor_types() == ("pdf", "pdf")
        assert _onlyoffice_types_for_file("report.pdf") == ("pdf", "pdf")


def test_onlyoffice_pdf_types_word_on_ds7(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("app.feature_flags.onlyoffice_ds_major", return_value=7):
        assert onlyoffice_pdf_editor_types() == ("word", "pdf")


def test_onlyoffice_editor_customization_pdf_autosave() -> None:
    pdf = onlyoffice_editor_customization(file_type="pdf")
    assert pdf["forcesave"] is True
    assert pdf["autosave"] is True
    docx = onlyoffice_editor_customization(file_type="docx")
    assert docx["forcesave"] is True
    assert "autosave" not in docx
