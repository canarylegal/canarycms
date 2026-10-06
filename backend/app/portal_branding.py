"""Client portal firm branding (title, logo)."""

from __future__ import annotations

from app.brand_config import DEFAULT_POWERED_BY_LABEL, DEFAULT_VENDOR_URL, resolve_powered_by, vendor_url
from app.models import FirmSettings

# Back-compat aliases (prefer brand_config / resolve_powered_by).
CANARY_LEGAL_SOFTWARE_URL = DEFAULT_VENDOR_URL
POWERED_BY_LABEL = DEFAULT_POWERED_BY_LABEL


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


def powered_by_for_portal(firm: FirmSettings | None) -> tuple[str, str, bool]:
    """Return (label, url, hide) for ``GET /portal/config``."""
    pb = resolve_powered_by(firm)
    # When hide is false but URL empty, fall back to vendor URL.
    url = pb.url or vendor_url()
    return pb.label, url, pb.hide
