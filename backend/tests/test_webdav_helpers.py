"""Unit tests for WebDAV and desktop-edit session helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.desktop_edit_session import webdav_session_hours
from app.routers.webdav import (
    _effective_webdav_media_type,
    _http_range_interval,
    _session_path_matches_filename,
)


def test_http_range_none() -> None:
    assert _http_range_interval(None, 100) is None
    assert _http_range_interval("", 100) is None
    assert _http_range_interval("bytes", 100) is None


def test_http_range_bytes_0_99() -> None:
    assert _http_range_interval("bytes=0-99", 200) == (0, 99)
    assert _http_range_interval("bytes=0-99", 50) == (0, 49)


def test_http_range_suffix() -> None:
    assert _http_range_interval("bytes=-20", 100) == (80, 99)
    assert _http_range_interval("bytes=-5", 5) == (0, 4)


def test_http_range_416() -> None:
    assert _http_range_interval("bytes=100-200", 50) == "416"
    assert _http_range_interval("bytes=-0", 100) == "416"
    assert _http_range_interval("bytes=0-10", 0) == "416"
    assert _http_range_interval("bytes=10-5", 100) == "416"


def test_session_path_matches_filename_case_insensitive() -> None:
    row = SimpleNamespace(original_filename="Folder/Report.DOCX")
    assert _session_path_matches_filename("Report.DOCX", row) is True
    assert _session_path_matches_filename("report.docx", row) is True
    assert _session_path_matches_filename("Report.DOC", row) is False


def test_effective_webdav_media_type_docx_octet_stream() -> None:
    row = SimpleNamespace(
        original_filename="letter.docx",
        mime_type="application/octet-stream",
    )
    assert (
        _effective_webdav_media_type(row)
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_effective_webdav_media_type_preserves_explicit() -> None:
    row = SimpleNamespace(
        original_filename="letter.docx",
        mime_type="application/pdf",
    )
    assert _effective_webdav_media_type(row) == "application/pdf"


def test_webdav_session_hours_clamp(monkeypatch) -> None:
    monkeypatch.setenv("WEBDAV_SESSION_HOURS", "8")
    assert webdav_session_hours() == 8
    monkeypatch.setenv("WEBDAV_SESSION_HOURS", "0")
    assert webdav_session_hours() == 1
    monkeypatch.setenv("WEBDAV_SESSION_HOURS", "999")
    assert webdav_session_hours() == 72
    monkeypatch.setenv("WEBDAV_SESSION_HOURS", "not-a-number")
    assert webdav_session_hours() == 8
    monkeypatch.delenv("WEBDAV_SESSION_HOURS", raising=False)
    assert webdav_session_hours() == 8
