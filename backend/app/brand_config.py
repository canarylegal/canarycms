"""Install brand / vendor configuration (Phase 2).

Env-backed product identity for the Canary kernel (and forks). Distinct from
firm *content* (letterheads, trading name, portal logo) in ``FirmSettings``.

Resolution for support inbox and portal powered-by:

1. Non-empty Admin override on ``FirmSettings`` (when a DB row is supplied)
2. ``CANARY_BRAND_*`` environment (with legacy aliases)
3. Built-in Canary Legal Software defaults

Product display name and TOTP/WebAuthn RP name are **env-only** (not Admin).
Core installs keep the Canary product name; forks override via env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# Built-in defaults for the upstream Canary product.
DEFAULT_PRODUCT_NAME = "Canary"
DEFAULT_VENDOR_URL = "https://canarylegalsoftware.co.uk"
DEFAULT_POWERED_BY_LABEL = "Powered by Canary Legal Software"
DEFAULT_SUPPORT_INBOX = "colin@canarylegalsoftware.co.uk"
DEFAULT_TOTP_ISSUER = "Canary"
DEFAULT_WEBAUTHN_RP_NAME = "Canary"

# Strings that must not appear under a proprietary / white-label profile.
PROPRIETARY_FORBIDDEN_SUBSTRINGS = (
    "canarylegalsoftware.co.uk",
    "Canary Legal Software",
    "colin@canarylegalsoftware.co.uk",
)


def _env(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.getenv(name)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return default


def _env_bool(*names: str, default: bool = False) -> bool:
    for name in names:
        raw = os.getenv(name)
        if raw is None or not str(raw).strip():
            continue
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return default


def product_name() -> str:
    """Staff/product chrome name. Env-only; not an Admin setting."""
    return _env("CANARY_BRAND_PRODUCT_NAME", default=DEFAULT_PRODUCT_NAME) or DEFAULT_PRODUCT_NAME


def vendor_url() -> str:
    return _env("CANARY_BRAND_VENDOR_URL", default=DEFAULT_VENDOR_URL) or DEFAULT_VENDOR_URL


def env_powered_by_label() -> str:
    return _env("CANARY_BRAND_POWERED_BY_LABEL", default=DEFAULT_POWERED_BY_LABEL) or DEFAULT_POWERED_BY_LABEL


def env_powered_by_url() -> str:
    return _env("CANARY_BRAND_POWERED_BY_URL", "CANARY_BRAND_VENDOR_URL", default=DEFAULT_VENDOR_URL) or DEFAULT_VENDOR_URL


def env_powered_by_hide() -> bool:
    return _env_bool("CANARY_BRAND_POWERED_BY_HIDE", default=False)


def env_support_inbox() -> str:
    return (
        _env("CANARY_BRAND_SUPPORT_INBOX", "CANARY_SUPPORT_INBOX", default=DEFAULT_SUPPORT_INBOX)
        or DEFAULT_SUPPORT_INBOX
    )


def totp_issuer() -> str:
    return _env("CANARY_BRAND_TOTP_ISSUER", "TOTP_ISSUER", default=DEFAULT_TOTP_ISSUER) or DEFAULT_TOTP_ISSUER


def webauthn_rp_name() -> str:
    return (
        _env("CANARY_BRAND_WEBAUTHN_RP_NAME", "WEBAUTHN_RP_NAME", default=DEFAULT_WEBAUTHN_RP_NAME)
        or DEFAULT_WEBAUTHN_RP_NAME
    )


def thunderbird_update_base_url() -> str:
    """Build-time / docs helper; XPI embed still uses hosting publish config."""
    return _env(
        "CANARY_BRAND_TB_UPDATE_BASE_URL",
        "CANARY_TB_UPDATE_BASE_URL",
        default=f"{DEFAULT_VENDOR_URL.rstrip('/')}/thunderbird",
    )


@dataclass(frozen=True)
class PoweredBy:
    label: str
    url: str
    hide: bool


def resolve_powered_by(firm: Any | None = None) -> PoweredBy:
    """Effective portal powered-by after Admin overrides."""
    hide = env_powered_by_hide()
    label = env_powered_by_label()
    url = env_powered_by_url()
    if firm is not None:
        if bool(getattr(firm, "brand_powered_by_hide", False)):
            hide = True
        override_label = (getattr(firm, "brand_powered_by_label", None) or "").strip()
        if override_label:
            label = override_label
        override_url = (getattr(firm, "brand_powered_by_url", None) or "").strip()
        if override_url:
            url = override_url
    return PoweredBy(label=label, url=url, hide=hide)


def resolve_support_inbox(firm: Any | None = None) -> str:
    if firm is not None:
        override = (getattr(firm, "brand_support_inbox", None) or "").strip()
        if override:
            return override
    return env_support_inbox()


def env_brand_snapshot() -> dict[str, str | bool]:
    """Env-layer defaults (no Admin overrides) — for Admin UI hints and tests."""
    return {
        "product_name": product_name(),
        "vendor_url": vendor_url(),
        "support_inbox": env_support_inbox(),
        "powered_by_label": env_powered_by_label(),
        "powered_by_url": env_powered_by_url(),
        "powered_by_hide": env_powered_by_hide(),
        "totp_issuer": totp_issuer(),
        "webauthn_rp_name": webauthn_rp_name(),
        "thunderbird_update_base_url": thunderbird_update_base_url(),
    }


def proprietary_leak_hits(values: dict[str, str | bool] | None = None) -> list[str]:
    """Return forbidden substrings found in string values of a brand snapshot."""
    snap = values if values is not None else env_brand_snapshot()
    hits: list[str] = []
    blob = " ".join(str(v) for v in snap.values() if not isinstance(v, bool))
    for needle in PROPRIETARY_FORBIDDEN_SUBSTRINGS:
        if needle.casefold() in blob.casefold():
            hits.append(needle)
    return hits
