"""HttpOnly session cookie helpers for staff browser auth."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.session_cookie import (
    SESSION_COOKIE_NAME,
    attach_session_cookie,
    clear_session_cookie,
    session_cookies_enabled,
    session_token_from_request,
)


def test_session_cookies_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CANARY_SESSION_COOKIE", raising=False)
    assert session_cookies_enabled() is True
    monkeypatch.setenv("CANARY_SESSION_COOKIE", "0")
    assert session_cookies_enabled() is False


def test_attach_and_read_session_cookie(monkeypatch) -> None:
    monkeypatch.setenv("CANARY_SESSION_COOKIE", "1")
    monkeypatch.setenv("CANARY_PUBLIC_URL", "https://canary.example")
    response = MagicMock()
    request = MagicMock()
    request.url.scheme = "https"
    request.headers = {}
    request.cookies = {}

    attach_session_cookie(response, "jwt-value", request=request)
    response.set_cookie.assert_called_once()
    kwargs = response.set_cookie.call_args.kwargs
    assert kwargs["key"] == SESSION_COOKIE_NAME
    assert kwargs["value"] == "jwt-value"
    assert kwargs["httponly"] is True
    assert kwargs["secure"] is True
    assert kwargs["samesite"] == "lax"

    request.cookies = {SESSION_COOKIE_NAME: "jwt-value"}
    assert session_token_from_request(request) == "jwt-value"

    clear_session_cookie(response, request=request)
    response.delete_cookie.assert_called()


def test_jwt_raw_prefers_bearer_then_cookie(monkeypatch) -> None:
    from fastapi.security import HTTPAuthorizationCredentials

    from app.deps import _jwt_raw_from_request

    monkeypatch.setenv("CANARY_SESSION_COOKIE", "1")
    request = MagicMock()
    request.headers = {}
    request.cookies = {SESSION_COOKIE_NAME: "from-cookie"}

    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="from-bearer")
    assert _jwt_raw_from_request(request, bearer) == "from-bearer"
    assert _jwt_raw_from_request(request, None) == "from-cookie"
