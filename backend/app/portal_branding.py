"""Client portal firm branding (title, logo)."""

from __future__ import annotations

from app.brand_config import DEFAULT_VENDOR_URL
from app.models import FirmSettings

# Back-compat alias.
CANARY_LEGAL_SOFTWARE_URL = DEFAULT_VENDOR_URL


def firm_display_name(firm: FirmSettings | None) -> str:
    if firm is None:
        return ""
    name = (firm.trading_name or "").strip()
    if name:
        return name
    return (firm.registered_company_name or "").strip()


def portal_title(firm: FirmSettings | None) -> str:
    name = firm_display_name(firm)
    return f"{name} Portal" if name else "Client Portal"
