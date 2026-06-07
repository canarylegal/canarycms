"""Unit tests for stored-secret encryption (DATA_ENCRYPTION_KEY vs legacy JWT_SECRET)."""

from __future__ import annotations

import base64
import hashlib
import os

import pytest
from cryptography.fernet import Fernet

from app import email_crypt


@pytest.fixture(autouse=True)
def _reset_crypt_module(monkeypatch: pytest.MonkeyPatch) -> None:
    email_crypt._legacy_decrypt_logged = False
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)


def _jwt_derived_fernet(jwt_secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(jwt_secret.encode()).digest())
    return Fernet(key)


def test_encrypt_without_data_key_uses_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "legacy-jwt-only")
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    enc = email_crypt.encrypt_password("secret-value")
    assert _jwt_derived_fernet("legacy-jwt-only").decrypt(enc.encode()).decode() == "secret-value"


def test_data_key_encrypt_and_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    data_key = Fernet.generate_key().decode()
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", data_key)
    monkeypatch.setenv("JWT_SECRET", "jwt-for-auth-only")
    enc = email_crypt.encrypt_password("graph-secret")
    assert email_crypt.decrypt_password(enc) == "graph-secret"
    assert not email_crypt.uses_legacy_encryption_key()


def test_decrypt_legacy_ciphertext_with_new_data_key(monkeypatch: pytest.MonkeyPatch) -> None:
    jwt = "shared-legacy-secret"
    legacy_enc = _jwt_derived_fernet(jwt).encrypt(b"portal-code").decode()
    data_key = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_SECRET", jwt)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", data_key)
    assert email_crypt.decrypt_password(legacy_enc) == "portal-code"
    assert email_crypt.needs_reencryption(legacy_enc)


def test_reencrypt_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    jwt = "shared-legacy-secret"
    legacy_enc = _jwt_derived_fernet(jwt).encrypt(b"smtp-pass").decode()
    data_key = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_SECRET", jwt)
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", data_key)
    assert email_crypt.needs_reencryption(legacy_enc)
    plain = email_crypt.decrypt_password(legacy_enc)
    new_enc = email_crypt.encrypt_password(plain)
    assert email_crypt.decrypt_password(new_enc) == "smtp-pass"
    assert not email_crypt.needs_reencryption(new_enc)


def test_missing_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        email_crypt.encrypt_password("x")
