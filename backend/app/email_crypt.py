"""Symmetric encryption for stored secrets (IMAP, Graph, portal codes, CalDAV).

Uses ``DATA_ENCRYPTION_KEY`` when set. Decrypt falls back to the legacy JWT_SECRET-derived
key for ciphertext written before the split. New ciphertext is always written with the primary key.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

_legacy_decrypt_logged = False


def _fernet_from_jwt_secret(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def _data_encryption_key_raw() -> str:
    return (os.getenv("DATA_ENCRYPTION_KEY") or "").strip()


def _jwt_secret_raw() -> str:
    return (os.getenv("JWT_SECRET") or "").strip()


def _primary_fernet() -> Fernet:
    data_key = _data_encryption_key_raw()
    if data_key:
        return Fernet(data_key.encode() if isinstance(data_key, str) else data_key)
    jwt = _jwt_secret_raw()
    if not jwt:
        raise RuntimeError("DATA_ENCRYPTION_KEY or JWT_SECRET must be configured")
    log.warning(
        "DATA_ENCRYPTION_KEY is not set; encrypting with JWT_SECRET-derived key (deprecated). "
        "Set DATA_ENCRYPTION_KEY and run scripts/reencrypt_data_secrets.py."
    )
    return _fernet_from_jwt_secret(jwt)


def _legacy_fernet() -> Fernet | None:
    """JWT-derived Fernet used before DATA_ENCRYPTION_KEY was introduced."""
    if not _data_encryption_key_raw():
        return None
    jwt = _jwt_secret_raw()
    if not jwt:
        return None
    return _fernet_from_jwt_secret(jwt)


def encrypt_password(plaintext: str) -> str:
    return _primary_fernet().encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    global _legacy_decrypt_logged
    primary = _primary_fernet()
    try:
        return primary.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        legacy = _legacy_fernet()
        if legacy is None:
            raise
        if not _legacy_decrypt_logged:
            log.warning(
                "Decrypting stored secret with legacy JWT_SECRET-derived key; "
                "run scripts/reencrypt_data_secrets.py after setting DATA_ENCRYPTION_KEY."
            )
            _legacy_decrypt_logged = True
        return legacy.decrypt(ciphertext.encode()).decode()


def decrypt_password_if_present(ciphertext: str | None) -> str | None:
    enc = (ciphertext or "").strip()
    if not enc:
        return None
    return decrypt_password(enc)


def uses_legacy_encryption_key() -> bool:
    """True when primary encrypt key is still derived from JWT_SECRET."""
    return not bool(_data_encryption_key_raw())


def needs_reencryption(ciphertext: str | None) -> bool:
    """True when ciphertext exists and was encrypted with the legacy key."""
    enc = (ciphertext or "").strip()
    if not enc or uses_legacy_encryption_key():
        return False
    legacy = _legacy_fernet()
    if legacy is None:
        return False
    try:
        _primary_fernet().decrypt(enc.encode())
        return False
    except InvalidToken:
        try:
            legacy.decrypt(enc.encode())
            return True
        except InvalidToken:
            return False
