"""Reject .env.example placeholders so a blind ``cp .env.example .env`` cannot go live."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def reject_insecure_placeholder(name: str, value: str) -> None:
    """Fail closed if a value is still an example placeholder (all '#', CHANGE_ME, …)."""
    stripped = (value or "").strip()
    if not stripped:
        return
    if all(ch == "#" for ch in stripped):
        raise RuntimeError(
            f"{name} is still the .env.example placeholder — generate a real secret "
            "(see docs/DEPLOYMENT.md §3)"
        )
    upper = stripped.upper()
    for marker in ("CHANGE_ME", "REPLACE_ME", "YOUR_CANARY", "PASTE_"):
        if marker in upper:
            raise RuntimeError(
                f"{name} still looks like a placeholder ({marker}) — generate a real secret "
                "(see docs/DEPLOYMENT.md §3)"
            )


def validate_core_secrets_at_startup() -> None:
    """Validate secrets that must be real before serving traffic."""
    jwt = (os.getenv("JWT_SECRET") or "").strip()
    if jwt:
        reject_insecure_placeholder("JWT_SECRET", jwt)
    data_key = (os.getenv("DATA_ENCRYPTION_KEY") or "").strip()
    if data_key:
        reject_insecure_placeholder("DATA_ENCRYPTION_KEY", data_key)
        try:
            Fernet(data_key.encode() if isinstance(data_key, str) else data_key)
        except Exception as exc:
            raise RuntimeError(
                "DATA_ENCRYPTION_KEY is not a valid Fernet key — generate with: "
                'python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            ) from exc
    for name in (
        "ONLYOFFICE_JWT_SECRET",
        "ONLYOFFICE_SECURE_LINK_SECRET",
        "POSTGRES_PASSWORD",
    ):
        raw = (os.getenv(name) or "").strip()
        if raw:
            reject_insecure_placeholder(name, raw)
