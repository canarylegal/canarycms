"""ONLYOFFICE Document Server version probing."""

from unittest.mock import MagicMock, patch

import pytest

from app import onlyoffice_ds_version as mod
from app.feature_flags import onlyoffice_pdf_editor_types


@pytest.fixture(autouse=True)
def _clear_version_cache() -> None:
    mod.invalidate_onlyoffice_ds_version_cache()
    yield
    mod.invalidate_onlyoffice_ds_version_cache()


def test_parse_major() -> None:
    assert mod._parse_major("9.0.3.29") == 9
    assert mod._parse_major("7.5.1") == 7


@patch("app.onlyoffice_ds_version.httpx.Client")
def test_probe_returns_major(client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_DS_INTERNAL_URL", "http://onlyoffice")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"error": 0, "version": "7.5.1.23"}
    client_cls.return_value.__enter__.return_value.post.return_value = resp
    assert mod._probe_onlyoffice_ds_major() == 7


def test_pdf_types_word_when_ds7_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_DS_MAJOR", "auto")
    monkeypatch.setenv("CANARY_OPEN_PDF_IN_ONLYOFFICE", "1")
    with patch("app.feature_flags.onlyoffice_ds_major", return_value=7):
        assert onlyoffice_pdf_editor_types() == ("word", "pdf")


def test_pdf_types_pdf_when_ds9_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_DS_MAJOR", "auto")
    with patch("app.feature_flags.onlyoffice_ds_major", return_value=9):
        assert onlyoffice_pdf_editor_types() == ("pdf", "pdf")
