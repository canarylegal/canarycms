"""Portal branding helpers."""

from __future__ import annotations

from app.portal_branding import firm_display_name, portal_title
from app.models import FirmSettings


def test_portal_title_from_trading_name() -> None:
    firm = FirmSettings(id=1, trading_name="Example Solicitors")
    assert firm_display_name(firm) == "Example Solicitors"
    assert portal_title(firm) == "Example Solicitors Portal"


def test_portal_title_fallback() -> None:
    assert portal_title(None) == "Client Portal"
