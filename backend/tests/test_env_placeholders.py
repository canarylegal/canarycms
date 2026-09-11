"""Reject .env.example placeholders at startup."""

from __future__ import annotations

import pytest

from app.env_placeholders import reject_insecure_placeholder, validate_core_secrets_at_startup


def test_reject_hash_placeholder() -> None:
    with pytest.raises(RuntimeError, match="placeholder"):
        reject_insecure_placeholder("JWT_SECRET", "#" * 40)


def test_reject_change_me_placeholder() -> None:
    with pytest.raises(RuntimeError, match="CHANGE_ME"):
        reject_insecure_placeholder("JWT_SECRET", "CHANGE_ME_generate_with_openssl")


def test_accept_real_looking_secret() -> None:
    reject_insecure_placeholder("JWT_SECRET", "a" * 32)


def test_validate_core_secrets_rejects_bad_fernet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-value")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", "CHANGE_ME_not_a_fernet_key")
    with pytest.raises(RuntimeError, match="placeholder|Fernet"):
        validate_core_secrets_at_startup()
