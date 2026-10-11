"""Edit-session ONLYOFFICE document key binding."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.desktop_edit_session import ensure_session_document_key, session_matches_document_key
from app.models import AuditEvent
from app.routers.onlyoffice import (
    _audit_oo_callback_persist_refused,
    _callback_fetch_url_or_reject,
    _is_allowed_onlyoffice_ds_fetch_path,
    _safe_url_for_log,
    _truncate_doc_key_for_audit,
)


def test_session_matches_document_key() -> None:
    sess = SimpleNamespace(document_key="file_1_abc")
    assert session_matches_document_key(sess, "file_1_abc") is True
    assert session_matches_document_key(sess, "other") is False
    assert session_matches_document_key(SimpleNamespace(document_key=None), "file_1_abc") is False
    assert session_matches_document_key(sess, "") is False


def test_callback_key_for_file_b_rejected_on_session_for_file_a() -> None:
    """A→B binding: active session for file A must not accept file B's document key."""
    sess_a = SimpleNamespace(document_key="file_A_v3_deadbeef")
    key_b = "file_B_v1_cafebabe"
    assert session_matches_document_key(sess_a, "file_A_v3_deadbeef") is True
    assert session_matches_document_key(sess_a, key_b) is False


def test_audit_oo_callback_key_mismatch_records_event() -> None:
    """A→B refuse path must emit a security audit row (no download URL in meta)."""
    adds: list[object] = []
    commits = {"n": 0}

    class FakeDb:
        def add(self, obj) -> None:
            adds.append(obj)

        def flush(self) -> None:
            pass

        def commit(self) -> None:
            commits["n"] += 1

    file_id = uuid.uuid4()
    case_id = uuid.uuid4()
    key_b = "file_B_v1_cafebabe_extra_long_suffix"
    _audit_oo_callback_persist_refused(
        FakeDb(),
        file_id=file_id,
        action="onlyoffice_callback_key_mismatch",
        reason="document_key_mismatch",
        callback_key=key_b,
        session_key="file_A_v3_deadbeef",
        case_id=case_id,
    )
    assert commits["n"] == 1
    assert len(adds) == 1
    ev = adds[0]
    assert isinstance(ev, AuditEvent)
    assert ev.action == "onlyoffice_callback_key_mismatch"
    assert ev.entity_id == str(file_id)
    assert ev.meta_json is not None
    assert "document_key_mismatch" in ev.meta_json
    assert "file_A_v3_deadbeef" in ev.meta_json
    assert _truncate_doc_key_for_audit(key_b) in ev.meta_json
    assert "http" not in ev.meta_json
    assert "url" not in ev.meta_json


def test_safe_url_for_log_strips_query_fragment_and_userinfo() -> None:
    assert (
        _safe_url_for_log(
            "https://user:secret@onlyoffice:8080/cache/files/x.bin?md5=tok&expires=1#frag"
        )
        == "https://onlyoffice:8080/cache/files/x.bin"
    )
    assert _safe_url_for_log(None) == "-"
    assert _safe_url_for_log("") == "-"


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
