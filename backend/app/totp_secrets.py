"""Encrypt TOTP secrets at rest (Fernet via email_crypt)."""

from __future__ import annotations

from cryptography.fernet import InvalidToken

from app.email_crypt import decrypt_password, encrypt_password, needs_reencryption


def encrypt_totp_secret(plaintext: str) -> str:
    return encrypt_password(plaintext)


def decrypt_totp_secret(stored: str | None) -> str | None:
    """Return plaintext TOTP secret; accepts legacy plaintext base32 rows."""
    enc = (stored or "").strip()
    if not enc:
        return None
    try:
        return decrypt_password(enc)
    except InvalidToken:
        # Historical rows stored raw pyotp base32.
        return enc


def normalize_stored_totp_secret(stored: str | None) -> tuple[str | None, bool]:
    """Return (ciphertext_to_store, changed). Re-encrypts plaintext or legacy-key ciphertext."""
    plain = decrypt_totp_secret(stored)
    if plain is None:
        return None, False
    if needs_reencryption(stored) or (stored or "").strip() == plain:
        return encrypt_totp_secret(plain), True
    return stored, False
