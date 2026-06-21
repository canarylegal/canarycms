"""Mail plugin authorization code validation and exchange."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.mail_plugin_auth_service import (
    validate_plugin_client,
    validate_plugin_redirect_uri,
    validate_plugin_state,
)


def test_validate_plugin_client_accepts_thunderbird_and_outlook() -> None:
    assert validate_plugin_client("thunderbird") == "thunderbird"
    assert validate_plugin_client("Outlook") == "outlook"


def test_validate_plugin_client_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_plugin_client("apple-mail")
    assert exc.value.status_code == 400


def test_validate_plugin_state_requires_length_and_charset() -> None:
    assert validate_plugin_state("a" * 16) == "a" * 16
    with pytest.raises(HTTPException):
        validate_plugin_state("short")
    with pytest.raises(HTTPException):
        validate_plugin_state("bad state with spaces")


def test_validate_plugin_redirect_uri_thunderbird() -> None:
    ext_uri = "moz-extension://12345678-1234-1234-1234-123456789abc/auth-callback.html"
    assert validate_plugin_redirect_uri("thunderbird", ext_uri) == ext_uri
    https_uri = "https://canary.example.com/connect/mail-plugin/callback"
    assert validate_plugin_redirect_uri("thunderbird", https_uri) == https_uri
    with pytest.raises(HTTPException):
        validate_plugin_redirect_uri("thunderbird", "https://evil.example/auth-callback.html")


def test_validate_plugin_redirect_uri_outlook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_PUBLIC_URL", "https://canary.example.com")
    expected = "https://canary.example.com/outlook-addin/auth-callback.html"
    assert validate_plugin_redirect_uri("outlook", expected) == expected
    with pytest.raises(HTTPException):
        validate_plugin_redirect_uri("outlook", "https://canary.example.com/outlook-addin/other.html")
