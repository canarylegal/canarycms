"""Edit-session ONLYOFFICE document key binding."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.desktop_edit_session import ensure_session_document_key, session_matches_document_key
from app.routers.onlyoffice import _callback_fetch_url_or_reject, _is_allowed_onlyoffice_ds_fetch_path


def test_session_matches_document_key() -> None:
    sess = SimpleNamespace(document_key="file_1_abc")
    assert session_matches_document_key(sess, "file_1_abc") is True
    assert session_matches_document_key(sess, "other") is False
    assert session_matches_document_key(SimpleNamespace(document_key=None), "file_1_abc") is False
    assert session_matches_document_key(sess, "") is False


def test_ensure_session_document_key_reuses_existing() -> None:
    sess = SimpleNamespace(document_key="existing-key")
    db = MagicMock()
    assert ensure_session_document_key(db, sess, candidate="new-key") == "existing-key"
    db.commit.assert_not_called()


def test_ensure_session_document_key_stores_candidate() -> None:
    sess = SimpleNamespace(document_key=None)
    adds: list[object] = []

    class FakeDb:
        def add(self, obj) -> None:
            adds.append(obj)

        def commit(self) -> None:
            pass

        def refresh(self, obj) -> None:
            pass

    out = ensure_session_document_key(FakeDb(), sess, candidate="minted-key")
    assert out == "minted-key"
    assert sess.document_key == "minted-key"
    assert adds == [sess]


def test_callback_fetch_rejects_unexpected_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_DS_INTERNAL_URL", "http://onlyoffice")
    assert _is_allowed_onlyoffice_ds_fetch_path("/cache/files/data/foo.bin") is True
    assert _is_allowed_onlyoffice_ds_fetch_path("/printfile/abc") is True
    assert _is_allowed_onlyoffice_ds_fetch_path("/admin") is False
    assert _callback_fetch_url_or_reject("http://evil.example/admin") is None
    allowed = _callback_fetch_url_or_reject("http://onlyoffice/cache/files/data/x")
    assert allowed is not None
    assert "/cache/files/" in allowed
