"""ONLYOFFICE documentType / fileType sniffing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.onlyoffice_file_types import _correct_file_type, _onlyoffice_types_for_file


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.doc", ("word", "doc")),
        ("a.docx", ("word", "docx")),
        ("a.dot", ("word", "dot")),
        ("a.dotx", ("word", "dotx")),
        ("a.odt", ("word", "odt")),
        ("a.rtf", ("word", "rtf")),
        ("a.txt", ("word", "txt")),
        ("b.xls", ("cell", "xls")),
        ("b.xlsx", ("cell", "xlsx")),
        ("b.xlsm", ("cell", "xlsm")),
        ("b.xlsb", ("cell", "xlsb")),
        ("b.ods", ("cell", "ods")),
        ("c.ppt", ("slide", "ppt")),
        ("c.pptx", ("slide", "pptx")),
        ("c.pps", ("slide", "pps")),
        ("c.ppsx", ("slide", "ppsx")),
        ("c.odp", ("slide", "odp")),
    ],
)
def test_onlyoffice_types_matrix(filename: str, expected: tuple[str, str]) -> None:
    assert _onlyoffice_types_for_file(filename) == expected


def test_onlyoffice_types_case_insensitive_extension() -> None:
    assert _onlyoffice_types_for_file("Brief.DOCX") == ("word", "docx")


def test_onlyoffice_types_unsupported() -> None:
    assert _onlyoffice_types_for_file("photo.png") is None
    assert _onlyoffice_types_for_file("archive.zip") is None


def test_onlyoffice_types_pdf_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_OPEN_PDF_IN_ONLYOFFICE", "1")
    with patch("app.feature_flags.onlyoffice_ds_major", return_value=9):
        assert _onlyoffice_types_for_file("report.pdf") == ("pdf", "pdf")


def test_onlyoffice_types_pdf_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_OPEN_PDF_IN_ONLYOFFICE", "0")
    assert _onlyoffice_types_for_file("report.pdf") is None


@pytest.mark.parametrize(
    ("claimed", "upgraded"),
    [
        ("doc", "docx"),
        ("dot", "dotx"),
        ("xls", "xlsx"),
        ("ppt", "pptx"),
        ("pps", "ppsx"),
    ],
)
def test_correct_file_type_upgrades_zip_magic(tmp_path: Path, claimed: str, upgraded: str) -> None:
    path = tmp_path / f"misnamed.{claimed}"
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 8)
    assert _correct_file_type(claimed, path) == upgraded


@pytest.mark.parametrize("claimed", ["doc", "xls", "ppt"])
def test_correct_file_type_keeps_ole_when_not_zip(tmp_path: Path, claimed: str) -> None:
    path = tmp_path / f"real.{claimed}"
    path.write_bytes(b"\xd0\xcf\x11\xe0")  # OLE compound document magic
    assert _correct_file_type(claimed, path) == claimed


def test_correct_file_type_leaves_modern_extensions(tmp_path: Path) -> None:
    path = tmp_path / "modern.docx"
    path.write_bytes(b"PK\x03\x04rest")
    assert _correct_file_type("docx", path) == "docx"


def test_correct_file_type_missing_file_keeps_claimed(tmp_path: Path) -> None:
    missing = tmp_path / "gone.doc"
    assert _correct_file_type("doc", missing) == "doc"
