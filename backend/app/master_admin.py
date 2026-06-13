"""Env-configured master recovery operator (break-glass; not a DB user)."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass

from app.security import verify_totp

log = logging.getLogger(__name__)

MASTER_RECOVERY_ROLE = "master_recovery"
MASTER_RECOVERY_SUB = "master_recovery"
MASTER_RECOVERY_USER_ID = "00000000-0000-0000-0000-000000000001"


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


@dataclass(frozen=True)
class MasterAdminConfig:
    login: str
    password: str
    require_2fa: bool
    totp_secret: str | None


def normalize_master_login(raw: str) -> str:
    return (raw or "").strip().lower()


def load_master_admin_config() -> MasterAdminConfig:
    login = normalize_master_login(_require_env("MASTER_ADMIN_LOGIN"))
    password = _require_env("MASTER_ADMIN_PASSWORD")
    if len(login) < 8:
        raise RuntimeError("MASTER_ADMIN_LOGIN must be at least 8 characters")
    if len(password) < 12:
        raise RuntimeError("MASTER_ADMIN_PASSWORD must be at least 12 characters")
    require_2fa = _env_bool("MASTER_ADMIN_REQUIRE_2FA", default=False)
    totp_secret = (os.getenv("MASTER_ADMIN_TOTP_SECRET") or "").strip() or None
    if require_2fa and not totp_secret:
        raise RuntimeError(
            "MASTER_ADMIN_TOTP_SECRET is required when MASTER_ADMIN_REQUIRE_2FA is enabled",
        )
    return MasterAdminConfig(
        login=login,
        password=password,
        require_2fa=require_2fa,
        totp_secret=totp_secret,
    )


def validate_master_admin_config_at_startup() -> None:
    load_master_admin_config()


def is_reserved_master_login(login: str) -> bool:
    try:
        cfg = load_master_admin_config()
    except RuntimeError:
        return False
    return normalize_master_login(login) == cfg.login


def verify_master_password(*, supplied: str, expected: str) -> bool:
    return secrets.compare_digest((supplied or "").encode("utf-8"), (expected or "").encode("utf-8"))


def try_authenticate_master(
    *,
    login: str,
    password: str,
    totp_code: str | None,
) -> tuple[bool, str | None]:
    """Return (ok, error_detail). error_detail is a short client-safe message."""

    try:
        cfg = load_master_admin_config()
    except RuntimeError:
        return False, None

    norm = normalize_master_login(login)
    if norm != cfg.login:
        return False, None
    if not verify_master_password(supplied=password, expected=cfg.password):
        return False, "Invalid credentials"

    if cfg.require_2fa:
        code = (totp_code or "").strip()
        if not code or not cfg.totp_secret:
            return False, "2FA required"
        if not verify_totp(secret=cfg.totp_secret, code=code):
            return False, "Invalid 2FA code"

    log.info("Master recovery operator signed in (login=%s)", norm)
    return True, None


def master_recovery_public_email(login: str) -> str:
    """Synthetic e-mail for UserPublic (EmailStr-compatible)."""

    safe = normalize_master_login(login).replace("@", "_")[:48]
    return f"recovery.{safe}@example.com"
