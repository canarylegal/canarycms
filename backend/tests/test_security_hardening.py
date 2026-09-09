"""Security hardening unit tests for audit, JWT default, upload MIME, and TOTP."""

from __future__ import annotations

import json
import os

import pytest
from fastapi import HTTPException
from jose import jwt

from app.audit import _safe_meta_json, log_event
from app.feature_flags import onlyoffice_callback_require_jwt
from app.routers.onlyoffice import _decode_callback_payload
from app.totp_secrets import decrypt_totp_secret, encrypt_totp_secret
from app.upload_limits import content_disposition_for_mime
from unittest.mock import MagicMock


def test_safe_meta_json_stays_valid_when_truncated() -> None:
    meta = {"note": "x" * 20_000, "ok": True}
    raw = _safe_meta_json(meta)
    assert len(raw) <= 8000
    parsed = json.loads(raw)
    assert parsed.get("_truncated") is True


def test_log_event_does_not_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    commits: list[str] = []
    adds: list[object] = []

    class FakeDb:
        def add(self, obj) -> None:
            adds.append(obj)

        def flush(self) -> None:
            pass

        def commit(self) -> None:
            commits.append("commit")

    monkeypatch.setenv("JWT_SECRET", "test-secret-for-audit")
    log_event(FakeDb(), actor_user_id=None, action="test.action", meta={"a": 1})
    assert adds
    assert commits == []


def test_onlyoffice_jwt_required_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ONLYOFFICE_CALLBACK_REQUIRE_JWT", raising=False)
    assert onlyoffice_callback_require_jwt() is True
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "test-onlyoffice-secret")
    body = {"status": 2, "key": "abc123"}
    req = MagicMock()
    req.headers = {}
    with pytest.raises(HTTPException) as exc:
        _decode_callback_payload(req, body)
    assert exc.value.status_code == 401


def test_onlyoffice_jwt_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_CALLBACK_REQUIRE_JWT", "0")
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "test-onlyoffice-secret")
    assert onlyoffice_callback_require_jwt() is False
    req = MagicMock()
    req.headers = {}
    out = _decode_callback_payload(req, {"status": 2, "key": "abc123"})
    assert out["key"] == "abc123"


def test_content_disposition_allowlist() -> None:
    assert content_disposition_for_mime("application/pdf", download=False) == "inline"
    assert content_disposition_for_mime("application/zip", download=False) == "attachment"
    assert content_disposition_for_mime("image/png", download=False) == "inline"
    assert content_disposition_for_mime("application/pdf", download=True) == "attachment"


def test_totp_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-value")
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    plain = "JBSWY3DPEHPK3PXP"
    enc = encrypt_totp_secret(plain)
    assert enc != plain
    assert decrypt_totp_secret(enc) == plain
    # Legacy plaintext still accepted
    assert decrypt_totp_secret(plain) == plain
