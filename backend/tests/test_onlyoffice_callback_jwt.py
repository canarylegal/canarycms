"""ONLYOFFICE callback JWT verification."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.routers.onlyoffice import _decode_callback_payload


def _request() -> MagicMock:
    req = MagicMock()
    req.headers = {}
    return req


def test_plain_callback_allowed_when_jwt_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "test-onlyoffice-secret")
    monkeypatch.delenv("ONLYOFFICE_CALLBACK_REQUIRE_JWT", raising=False)
    body = {"status": 2, "key": "abc123", "url": "http://onlyoffice/cache/files/x"}
    out = _decode_callback_payload(_request(), body)
    assert out["status"] == 2
    assert out["key"] == "abc123"


def test_plain_callback_rejected_when_jwt_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", "test-onlyoffice-secret")
    monkeypatch.setenv("ONLYOFFICE_CALLBACK_REQUIRE_JWT", "1")
    body = {"status": 2, "key": "abc123"}
    with pytest.raises(HTTPException) as exc:
        _decode_callback_payload(_request(), body)
    assert exc.value.status_code == 401


def test_signed_callback_body_token_accepted_when_jwt_required(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-onlyoffice-secret"
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", secret)
    monkeypatch.setenv("ONLYOFFICE_CALLBACK_REQUIRE_JWT", "1")
    payload = {"status": 6, "key": "signed-key", "url": "http://onlyoffice/cache/files/y"}
    token = jwt.encode(payload, secret, algorithm="HS256")
    body = {"token": token}
    out = _decode_callback_payload(_request(), body)
    assert out["key"] == "signed-key"
    assert out["status"] == 6


def test_bearer_jwt_accepted_when_jwt_required(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-onlyoffice-secret"
    monkeypatch.setenv("ONLYOFFICE_JWT_SECRET", secret)
    monkeypatch.setenv("ONLYOFFICE_CALLBACK_REQUIRE_JWT", "1")
    payload = {"status": 2, "key": "bearer-key"}
    token = jwt.encode(payload, secret, algorithm="HS256")
    req = _request()
    req.headers = {"Authorization": f"Bearer {token}"}
    out = _decode_callback_payload(req, {"status": 2, "key": "ignored"})
    assert out["key"] == "bearer-key"
